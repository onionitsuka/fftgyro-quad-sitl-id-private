"""Observer/interface tests; no flight, hardware or network connection."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import numpy as np
from velocity_assist import VelocityObserver, VelocityAssist, stick_target, sim
from research_backend import sensors
from pilot_zero import PilotZero

CONFIG=json.loads((Path(__file__).parent/'research_model/model.json').read_text())


class AssistTests(unittest.TestCase):
    def test_imu_integration_and_landed_reset(self):
        observer=VelocityObserver(CONFIG,1.225,'imu')
        observer.update([0,0,-sim.G],[0,0,0],[0]*4,False,0)
        for _ in range(50):
            observer.update([1,0,-sim.G],[0,0,0],[450]*4,True,.2)
        np.testing.assert_allclose(observer.v,[1,0,.2],atol=1e-12)
        observer.update([0,0,-sim.G],[0,0,0],[0]*4,True,0,landed=True)
        np.testing.assert_allclose(observer.v,0,atol=1e-12)

    def test_level_initialization_and_no_future_samples(self):
        observer=VelocityObserver(CONFIG,1.225)
        q=sim.attitude(.1,-.2); f=sim.rotation(q).T@[0,0,-sim.G]
        observer.update(f,[0,0,0],[0]*4,False,0)
        np.testing.assert_allclose(observer.q,q,atol=1e-12)
        for _ in range(100): observer.update(f,[0,0,0],[450]*4,True,0)
        np.testing.assert_allclose(observer.v,0,atol=1e-12)
        self.assertEqual(observer.corrections,0)  # startup gate

    def test_aero_correction_runs_and_is_bounded(self):
        observer=VelocityObserver(CONFIG,1.225)
        observer.update([0,0,-sim.G],[0,0,0],[0]*4,False,0)
        for _ in range(500):
            observer.update([0,0,-sim.G],[0,0,0],[450]*4,True,0)
            self.assertLessEqual(np.linalg.norm(observer.last_correction),2*(1-np.exp(-.4))+1e-12)
        self.assertGreater(observer.corrections,0)
        self.assertTrue(np.isfinite(observer.v).all())

    def test_stick_axes_and_limits(self):
        q=[1,0,0,0]
        np.testing.assert_allclose(stick_target([0,0,500,0],q)[0],0)
        np.testing.assert_allclose(stick_target([1000,0,1000,0],q)[0],[2,0,-1])
        target,yaw=stick_target([1000,1000,0,1000],q)
        self.assertAlmostEqual(np.linalg.norm(target[:2]),2)
        self.assertAlmostEqual(target[2],1); self.assertAlmostEqual(yaw,np.pi/4)
        yaw90=[2**-.5,0,0,2**-.5]
        np.testing.assert_allclose(stick_target([1000,0,500,0],yaw90)[0],[0,2,0],atol=1e-12)

    def test_assist_sensor_stream_contains_no_navigation_truth(self):
        plant=SimpleNamespace(x=np.r_[np.arange(6),1.,0,0,0,0,0,0],dt=.004,force=np.array([0,0,-sim.G]))
        link=SimpleNamespace(mav=Mock())
        sensors(plant,link,25,np.random.default_rng(1),external_navigation=False)
        self.assertEqual(link.mav.hil_sensor_send.call_count,3)
        link.mav.hil_gps_send.assert_not_called()
        link.mav.hil_state_quaternion_send.assert_not_called()

    def test_manual_timeout_stops_setpoints_without_autoarming(self):
        assist=VelocityAssist.__new__(VelocityAssist)
        assist.pilot_zero=PilotZero();assist.zero_button=SimpleNamespace(poll=lambda:False)
        assist.observer=VelocityObserver(CONFIG,1.225,'imu')
        assist.link=SimpleNamespace(mav=Mock()); assist.system=11
        assist.received=True;assist.last_heartbeat=10.;assist.landed=False
        assist.vz=0.;assist.baro_reference=None;assist.rest_seconds=0.
        assist.vertical_position=0.
        assist.poll=lambda:10.;assist.manual_time=0.
        assist.manual=np.array([1000,0,500,0]);assist.mode=6;assist.last_mode_request=0
        assist.update([0,0,-sim.G],[0,0,0],[450]*4,True,10000000)
        assist.link.mav.set_position_target_local_ned_send.assert_not_called()
        assist.link.mav.command_long_send.assert_not_called()
        assist.manual_time=10.;assist.mode=3
        assist.update([0,0,-sim.G],[0,0,0],[450]*4,True,10020000)
        assist.link.mav.set_position_target_local_ned_send.assert_called_once()
        assist.link.mav.set_mode_send.assert_called_once()
        assist.link.mav.command_long_send.assert_not_called()

    def test_stationary_hypothesis_uses_pressure_not_true_contact(self):
        assist=VelocityAssist.__new__(VelocityAssist)
        assist.pilot_zero=PilotZero();assist.zero_button=SimpleNamespace(poll=lambda:False)
        assist.observer=VelocityObserver(CONFIG,1.225,'imu')
        assist.link=SimpleNamespace(mav=Mock());assist.system=11
        assist.poll=lambda:10.;assist.received=False;assist.landed=False;assist.vz=0.
        assist.baro_reference=None;assist.rest_seconds=0.
        assist.vertical_position=0.
        f=[0,0,-sim.G];gyro=[0,0,0]
        rpm=np.array([5000,0,5000,0])*2*np.pi/60
        def pressure(h):return 1013.25*(1-h/44330)**5.255
        assist.update(f,gyro,rpm,False,1000000,pressure(488))
        for i in range(30): assist.update(f,gyro,rpm,True,1020000+i*20000,pressure(489))
        self.assertFalse(assist.zero_motion)  # one metre above takeoff height
        assist.observer.v[:2]=[2,-1]
        for i in range(30): assist.update(f,gyro,rpm,True,2020000+i*20000,pressure(488))
        self.assertTrue(assist.zero_motion)
        np.testing.assert_allclose(assist.observer.v,0)

    def test_baro_vertical_speed_tracks_without_px4_state_feedback(self):
        assist=VelocityAssist.__new__(VelocityAssist)
        assist.pilot_zero=PilotZero();assist.zero_button=SimpleNamespace(poll=lambda:False)
        assist.observer=VelocityObserver(CONFIG,1.225,'imu')
        assist.link=SimpleNamespace(mav=Mock());assist.system=11
        assist.poll=lambda:10.;assist.received=False;assist.landed=False;assist.vz=0.
        assist.baro_reference=None;assist.rest_seconds=0.;assist.vertical_position=0.
        f=[0,0,-sim.G];gyro=[0,0,0];rotor=np.full(4,5000)*2*np.pi/60
        def pressure(h):return 1013.25*(1-h/44330)**5.255
        assist.update(f,gyro,rotor,False,1000000,pressure(488))
        for i in range(1,251):
            assist.update(f,gyro,rotor,True,1000000+i*20000,pressure(488+.5*i*.02))
        self.assertAlmostEqual(assist.vz,-.5,delta=.02)
        self.assertAlmostEqual(assist.vertical_position,-2.5,delta=.02)

    def test_pilot_zero_reaches_odometry_with_reset_counter(self):
        assist=VelocityAssist.__new__(VelocityAssist)
        assist.pilot_zero=PilotZero();assist.zero_button=SimpleNamespace(poll=lambda:True)
        assist.observer=VelocityObserver(CONFIG,1.225,'imu')
        assist.observer.v[:2]=[.6,-.2]
        assist.link=SimpleNamespace(mav=Mock());assist.system=11
        assist.poll=lambda:10.;assist.received=True;assist.last_heartbeat=10.
        assist.landed=False;assist.vz=0.;assist.vertical_position=0.
        assist.baro_reference=None;assist.rest_seconds=0.
        assist.manual_time=10.;assist.manual=np.array([0,0,500,0]);assist.mode=6
        estimate=assist.update([0,0,-sim.G],[0,0,0],[450]*4,True,10000000)
        np.testing.assert_allclose(estimate,0)
        np.testing.assert_allclose(assist.observer.v[:2],[.6,-.2])
        args=assist.link.mav.odometry_send.call_args.args
        np.testing.assert_allclose(args[7:10],0)
        self.assertEqual(args[15],1)
        assist.link.mav.statustext_send.assert_called_once()


if __name__=='__main__': unittest.main()
