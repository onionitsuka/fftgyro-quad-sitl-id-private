"""Causal IMU/RPM horizontal observer and a loopback-only PX4 velocity assist.

No plant position, velocity, attitude or wind is accepted by the observer.
Vertical velocity is a causal barometric/IMU estimate; horizontal odometry has no
position observations. This is an experimental assist, not independent EV.
"""
from collections import deque
import copy
import time
import numpy as np
from pymavlink import mavutil
from research_plant import sim
from pilot_zero import PilotZero, PilotZeroButton


def stick_target(sticks,q):
    """Heading-relative stick input -> NED velocity and yaw rate, no position."""
    def dead(v):
        return np.sign(v)*max(0,abs(v)-.08)/.92
    fwd,right=dead(sticks[0]/1000),dead(sticks[1]/1000)
    horizontal=np.array([fwd,right]); horizontal/=max(1.,np.linalg.norm(horizontal))
    rotation=sim.rotation(q); yaw=np.arctan2(rotation[1,0],rotation[0,0])
    north=np.cos(yaw)*horizontal[0]-np.sin(yaw)*horizontal[1]
    east=np.sin(yaw)*horizontal[0]+np.cos(yaw)*horizontal[1]
    return np.array([2*north,2*east,-dead((sticks[2]-500)/500)]),dead(sticks[3]/1000)*np.pi/4


class VelocityObserver:
    dt=.02
    def __init__(self,config,density,method='aero'):
        if method not in ('aero','imu'): raise ValueError('Unknown observer method')
        self.model=sim.Loads(copy.deepcopy(config),True,'measured')
        self.density_scale=density/self.model.cfg.rho
        self.method=method
        self.v=np.zeros(3); self.q=np.array([1.,0.,0.,0.])
        self.samples=deque(maxlen=10); self.static=deque(maxlen=50)
        self.armed_seconds=0.; self.count=0; self.corrections=0
        self.last_correction=np.zeros(2); self.skipped='disarmed'

    def update(self,force,gyro,rotor,armed,baro_vz,landed=False):
        force,gyro,rotor=map(lambda a:np.asarray(a,float),(force,gyro,rotor))
        if not np.isfinite(np.r_[force,gyro,rotor,baro_vz]).all():
            raise ValueError('Nonfinite observer input')
        if not armed or landed:
            self.v[:]=0; self.armed_seconds=0.; self.samples.clear()
            self.static.append(force.copy())
            f=np.mean(self.static,axis=0)
            roll=np.arctan2(-f[1],-f[2]); pitch=np.arctan2(f[0],np.hypot(f[1],f[2]))
            # Land detection is PX4's sensor-based result, not plant contact.
            # Preserve heading across a landing/takeoff cycle.
            r=sim.rotation(self.q); yaw=np.arctan2(r[1,0],r[0,0])
            tilt=sim.attitude(roll,pitch)
            qz=np.array([np.cos(yaw/2),0,0,np.sin(yaw/2)])
            self.q=np.r_[qz[0]*tilt[0]-qz[1:]@tilt[1:],
                qz[0]*tilt[1:]+tilt[0]*qz[1:]+np.cross(qz[1:],tilt[1:])]
            self.skipped='landed' if armed else 'disarmed'
            return self.v.copy()
        self.armed_seconds+=self.dt
        self.count+=1
        q=self.q
        self.q+=.5*self.dt*np.r_[-q[1:]@gyro,q[0]*gyro+np.cross(q[1:],gyro)]
        self.q/=np.linalg.norm(self.q)
        rotation=sim.rotation(self.q)
        self.v+=self.dt*(rotation@force+[0,0,sim.G])
        self.v[2]=baro_vz
        self.samples.append((force.copy(),gyro.copy(),rotor.copy()))
        self.last_correction[:]=0
        if self.method=='imu':
            self.skipped='IMU integration only'; return self.v.copy()
        if self.armed_seconds<7 or len(self.samples)<10:
            self.skipped='7 s startup gate'; return self.v.copy()
        if self.count%10: return self.v.copy()
        f,w,om=[np.mean([s[j] for s in self.samples],axis=0) for j in range(3)]
        if min(om)*60/(2*np.pi)<3500:
            self.skipped='low RPM'; return self.v.copy()
        def loads(v):
            air=rotation.T@v
            return self.density_scale*self.model(air,w,om,np.zeros(4))[:3]
        try:
            predicted=loads(self.v)
            jac=np.empty((3,2))
            for j in range(2):
                dv=np.zeros(3);dv[j]=.02
                jac[:,j]=(loads(self.v+dv)-loads(self.v-dv))/.04
            residual=self.model.mass*f-predicted
            correction=np.linalg.solve(jac.T@jac+.25*np.eye(2),jac.T@residual)
            correction*=min(1.,2/max(np.linalg.norm(correction),1e-12))
            correction*=1-np.exp(-.2/.5)
            self.v[:2]+=correction
            self.last_correction=correction
            self.corrections+=1;self.skipped=''
        except ValueError as exc:
            # Retain IMU propagation if the aerodynamic model is out of domain.
            self.skipped=str(exc)
        return self.v.copy()


class VelocityAssist:
    def __init__(self,config,density,port,system,method='aero'):
        self.observer=VelocityObserver(config,density,method)
        self.link=mavutil.mavlink_connection(f'udpin:127.0.0.1:{port}',source_system=250,source_component=191)
        self.system=system;self.manual=np.array([0.,0.,500.,0.])
        self.manual_time=-1e6;self.vz=0.;self.mode=0;self.armed=False
        self.last_request=-1e6;self.last_mode_request=-1e6;self.target=np.zeros(3)
        self.received=False;self.last_heartbeat=-1e6
        self.landed=True
        self.baro_reference=None;self.rest_seconds=0.;self.zero_motion=False
        self.vertical_position=0.
        self.pilot_zero=PilotZero()
        # Do not consume the pilot's button in isolated regression instances.
        self.zero_button=PilotZeroButton(enabled=system==9)
        self.output_velocity=np.zeros(3)

    def poll(self):
        now=time.monotonic()
        for _ in range(200):
            msg=self.link.recv_match(blocking=False)
            if msg is None: break
            if msg.get_srcSystem()!=self.system: continue
            self.received=True
            if msg.get_type()=='MANUAL_CONTROL':
                # INT16_MAX denotes an unavailable MAVLink axis, not full stick.
                if max(abs(msg.x),abs(msg.y),abs(msg.r))<=1000 and 0<=msg.z<=1000:
                    self.manual=np.array([msg.x,msg.y,msg.z,msg.r],float);self.manual_time=now
            elif msg.get_type()=='HEARTBEAT':
                self.mode=(msg.custom_mode>>16)&255
                self.armed=bool(msg.base_mode&mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            elif msg.get_type()=='EXTENDED_SYS_STATE':
                self.landed=msg.landed_state==mavutil.mavlink.MAV_LANDED_STATE_ON_GROUND
        if self.received and now-self.last_request>5:
            for mid,hz in [(69,50),(0,5),(245,50)]:
                self.link.mav.command_long_send(self.system,1,511,0,mid,1e6/hz,0,0,0,0,0)
            self.last_request=now
        return now

    def update(self,force,gyro,rotor,armed,stamp,pressure_hpa=None):
        now=self.poll();m=mavutil.mavlink
        # A drifting horizontal estimate can prevent PX4's own landing flag.
        # Flat-ground stationary hypothesis: near the takeoff barometric height,
        # insufficient rotor thrust for hover, quiet gyro and specific force ~1g.
        # This is a sensor-based zero-motion update, never a true-contact input.
        baro_height=None
        if pressure_hpa is not None and np.isfinite(pressure_hpa) and pressure_hpa>0:
            altitude=44330*(1-(pressure_hpa/1013.25)**(1/5.255))
            if self.baro_reference is None or not armed: self.baro_reference=altitude
            baro_height=altitude-self.baro_reference
        available_thrust=self.observer.density_scale*self.observer.model.cfg.kf*np.sum(np.asarray(rotor)**2)
        rest=(baro_height is not None and abs(baro_height)<.25
              and available_thrust<.65*self.observer.model.mass*sim.G and np.linalg.norm(gyro)<.15
              and abs(np.linalg.norm(force)-sim.G)<.5)
        self.rest_seconds=self.rest_seconds+self.observer.dt if rest else 0.
        self.zero_motion=self.landed or self.rest_seconds>=.5
        # Do not feed PX4's own vertical estimate back as an EV measurement.
        # A critically damped baro/IMU observer supplies a separate causal
        # vertical channel. A huge EV variance also poisoned EKF velocity resets.
        dt=self.observer.dt
        if not armed or self.zero_motion:
            self.vertical_position=-baro_height if baro_height is not None else 0.
            self.vz=0.
        else:
            az=(sim.rotation(self.observer.q)@force)[2]+sim.G
            self.vertical_position+=dt*self.vz+.5*dt*dt*az
            self.vz+=dt*az
            if baro_height is not None:
                error=-baro_height-self.vertical_position
                self.vertical_position+=2*dt/.5*error
                self.vz+=dt/(.5**2)*error
        estimated=self.observer.update(force,gyro,rotor,armed,self.vz,self.zero_motion)
        request=self.zero_button.poll()
        before=self.pilot_zero.count
        estimated=self.pilot_zero.apply(estimated,request=request,
            ground=not armed or self.zero_motion)
        self.output_velocity=estimated.copy()
        if self.pilot_zero.count!=before:
            print(f'PILOT ZERO horizontal NED bias={self.pilot_zero.bias.tolist()} m/s',flush=True)
            if self.received:
                self.link.mav.statustext_send(m.MAV_SEVERITY_INFO,b'Pilot zero: horizontal speed reset')
        if not self.received: return estimated
        if now-self.last_heartbeat>1:
            self.link.mav.heartbeat_send(m.MAV_TYPE_ONBOARD_CONTROLLER,m.MAV_AUTOPILOT_INVALID,0,0,0)
            self.last_heartbeat=now
        pose_cov=[float('nan')]+[0.]*20
        vel_cov=[0.]*21;vel_cov[0]=vel_cov[6]=vel_cov[11]=.25
        # Velocity-only external observation. Position and attitude are absent.
        self.link.mav.odometry_send(stamp,m.MAV_FRAME_LOCAL_NED,m.MAV_FRAME_LOCAL_NED,
            float('nan'),float('nan'),float('nan'),[float('nan')]*4,
            *estimated,float('nan'),float('nan'),float('nan'),pose_cov,vel_cov,
            self.pilot_zero.reset_counter,m.MAV_ESTIMATOR_TYPE_VIO,100)
        fresh=now-self.manual_time<.5
        sticks=self.manual if fresh else np.array([0,0,500,0.])
        self.target,yaw_rate=stick_target(sticks,self.observer.q)
        if fresh or not armed:
            # No position setpoint: sticks command velocity, centered = zero.
            mask=1|2|4|64|128|256|1024
            self.link.mav.set_position_target_local_ned_send(stamp//1000,self.system,1,
                m.MAV_FRAME_LOCAL_NED,mask,0,0,0,*self.target,0,0,0,0,yaw_rate)
            # Preserve the user's Position button: in this explicit assist
            # profile it requests velocity-only Offboard. Stabilized/Land/Disarm
            # are never overridden, and arming is always the user's action.
            if self.mode==3 and now-self.last_mode_request>1:
                self.link.mav.set_mode_send(self.system,m.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,6<<16)
                self.last_mode_request=now
        return estimated

    def close(self):
        self.zero_button.close()
        self.link.close()
