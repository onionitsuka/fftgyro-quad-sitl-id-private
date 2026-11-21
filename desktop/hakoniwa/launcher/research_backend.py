"""PX4 HIL + frozen research model + Hakoniwa physics and official Avatar PDUs."""
import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import socket
import time
import numpy as np
os.environ['MAVLINK20']='1'
from pymavlink import mavutil
from research_plant import Plant, ROOT, HERE, sim
from research_pdu import Avatar
from simulation_battery import SimulationBattery

def sensors(plant,link,step,rng,force=None,external_navigation=True):
    x=plant.x; stamp=1000000+round(step*plant.dt*1e6)
    force=plant.force if force is None else force
    r=sim.rotation(x[6:10]); alt=488-x[2]
    mag=r.T@np.array([.22,.006,.43])+rng.normal(0,.0005,3)
    pressure=1013.25*(1-alt/44330)**5.255+rng.normal(0,.001)
    for sid in (1,2,0):
        link.mav.hil_sensor_send(stamp,*force,*x[10:13],*mag,pressure,0,alt,20,63 if sid==2 else 8191,sid)
    lat=round((47.397742+math.degrees(x[0]/6378137))*1e7)
    lon=round((8.545594+math.degrees(x[1]/(6378137*math.cos(math.radians(47.397742)))))*1e7)
    if external_navigation and step%25==0:
        cog=round(np.degrees(np.arctan2(x[4],x[3]))%360*100)%36000
        link.mav.hil_gps_send(stamp,3,lat,lon,round(alt*1000),20,30,round(np.linalg.norm(x[3:5])*100),*[round(v*100) for v in x[3:6]],cog,14)
    if external_navigation and step%5==0:
        link.mav.hil_state_quaternion_send(stamp,x[6:10].tolist(),*x[10:13],lat,lon,round(alt*1000),*[round(v*100) for v in x[3:6]],0,0,*[round(v/sim.G*1000) for v in plant.force])
    return pressure

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',choices=['identified','existing'],default='identified')
    parser.add_argument('--route',choices=['command_route','measured'],default='command_route')
    parser.add_argument('--voltage',type=float,default=16.)
    parser.add_argument('--density',type=float)
    parser.add_argument('--direct-roll',action='store_true')
    parser.add_argument('--wind-ned',type=float,nargs=3,default=[0.,0.,0.],metavar=('N','E','D'))
    parser.add_argument('--port',type=int,default=4568)
    parser.add_argument('--assist',choices=['none','aero','imu'],default='none')
    parser.add_argument('--assist-port',type=int,default=14808)
    parser.add_argument('--system',type=int,default=9)
    parser.add_argument('--battery-port',type=int,default=14908)
    parser.add_argument('--accel-bias',type=float,nargs=3,default=[0.,0.,0.])
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not np.isfinite(args.accel_bias).all(): raise ValueError('IMU bias must be finite')
    if not 14.07<=args.voltage<=16.36: raise ValueError('Voltage outside motor calibration range 14.07..16.36 V')
    if args.density is not None and not 1.0<=args.density<=1.4: raise ValueError('Density outside configured range')
    if not np.isfinite(args.wind_ned).all() or np.linalg.norm(args.wind_ned)>10:
        raise ValueError('Configured wind must be finite and at most 10 m/s')
    plant=Plant(args.model,args.route,args.voltage,args.density,False if args.direct_roll else None)
    battery=SimulationBattery(args.battery_port,args.system,plant.voltage)
    avatar=Avatar(ROOT)
    assist=None
    if args.assist!='none':
        from velocity_assist import VelocityAssist
        assist=VelocityAssist(plant.config,plant.density,args.assist_port,args.system,args.assist)
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=dict(model_id=plant.config['id'],variant=args.model,route=args.route,
        model_sha256=hashlib.sha256((HERE/'research_model/model.json').read_bytes()).hexdigest(),
        rpm_source='simulation_generated_command_voltage',flight_fit=False,
        physics='official Hakoniwa v5 acceleration library; Python midpoint integration',
        controller='PX4 SITL; QGC USB joystick',dt=plant.dt,voltage=args.voltage,density=plant.density,
        battery='constant voltage shared with motor model; 5 Hz BATTERY_STATUS; no discharge dynamics',
        assist=args.assist,assist_navigation='IMU/RPM horizontal + causal barometric/IMU vertical velocity; no PX4 state feedback or HIL GPS/state' if assist else 'synthetic GPS',
        accel_bias_m_s2=args.accel_bias,
        pilot_zero='InterLink Linux button 0: pilot-declared horizontal rest; persistent NED output offset; clears on landing/disarm' if assist else None,
        wind_ned_m_s=args.wind_ned,wind_transition_s=2.,
        roll_transfer=plant.config.get('roll_transfer',False),mass=plant.vehicle.mass,inertia=plant.vehicle.inertia.tolist(),
        startup='extra loads off below minimum rotor 3000 rpm; smooth ramp to full at minimum 3500 rpm; unvalidated startup extension',
        ground='unilateral flat ground support; no ground effect or obstacle collision',
        limits='11.5 m/s airspeed; ambiguous induced-flow roots stop the session',
        gyro_density='rotor angular momentum not density-scaled',
        settings=plant.config)
    (args.output/'research-manifest.json').write_text(json.dumps(manifest,indent=2))
    print(f'RESEARCH READY model={args.model} route={args.route} voltage={args.voltage} V',flush=True)
    link=mavutil.mavlink_connection(f'tcpin:127.0.0.1:{args.port}',source_system=250)
    deadline=time.monotonic()+40
    while link.port is None:
        link.recv_match(blocking=False)
        if time.monotonic()>deadline: raise TimeoutError('PX4 HIL connection timeout')
        time.sleep(.005)
    print('PX4 research HIL connected',flush=True)
    link.port.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
    step=0; command=np.zeros(4); armed=False; got_actuator=False
    rng=np.random.default_rng(20261112); wall=time.monotonic(); last_actuator=wall
    started=False; previous_flags=None
    imu_force=[]; imu_gyro=[]
    assist_stream=(args.output/'velocity-assist.csv').open('w',newline='') if assist else None
    if assist:
        assist_writer=csv.writer(assist_stream)
        assist_writer.writerow(['time_s','estimated_vn','estimated_ve','baro_vd','true_vn','true_ve','true_vd',
            'target_vn','target_ve','target_vd','corrections','observer_status','px4_mode',
            'raw_vn','raw_ve','zero_bias_n','zero_bias_e','pilot_zero_count','odom_reset_counter'])
    with (args.output/'research-flight.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['time_s','armed',*[f'x{i}' for i in range(13)],*[f'rpm{i+1}' for i in range(4)],*[f'command{i+1}' for i in range(4)],*sim.AXES,'wind_n','wind_e','wind_d','support_flags'])
        try:
            while True:
                state=avatar.poll(step*plant.dt)
                if state!=2:
                    if started:
                        raise RuntimeError('箱庭が停止しました。アプリ一覧の「箱庭を再起動」で復旧してください。')
                    wall=time.monotonic(); last_actuator=wall
                    time.sleep(.005); continue
                started=True
                measured_force=plant.force+np.asarray(args.accel_bias)
                if step%50==0: battery.publish()
                pressure=sensors(plant,link,step,rng,measured_force,external_navigation=assist is None)
                imu_force.append(measured_force.copy()); imu_gyro.append(plant.x[10:13].copy())
                if assist and step%5==0:
                    # Integrate the full preceding IMU interval, including brief
                    # contact impulses, rather than decimating a 250 Hz sample.
                    velocity=assist.update(np.mean(imu_force,axis=0),np.mean(imu_gyro,axis=0),plant.rotor,armed,
                        1000000+round(step*plant.dt*1e6),pressure)
                    # Truth enters only this evaluation log, not the observer.
                    assist_writer.writerow([step*plant.dt,*velocity,*plant.x[3:6],*assist.target,
                        assist.observer.corrections,assist.observer.skipped,assist.mode,
                        *assist.observer.v[:2],*assist.pilot_zero.bias,assist.pilot_zero.count,assist.pilot_zero.reset_counter])
                if step%5==0: imu_force.clear(); imu_gyro.clear()
                msg=link.recv_match(type='HIL_ACTUATOR_CONTROLS',blocking=True,timeout=.03 if got_actuator else .001)
                while msg is None and got_actuator:
                    if time.monotonic()-last_actuator>3: raise RuntimeError('PX4 actuator stream lost')
                    # Wait for this sensor tick's output; do not resend the same IMU timestamp.
                    msg=link.recv_match(type='HIL_ACTUATOR_CONTROLS',blocking=True,timeout=.03)
                if msg is not None:
                    command=np.array(msg.controls[:4]); armed=bool(msg.mode&mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                    last_actuator=time.monotonic(); got_actuator=True
                wind=avatar.wind()+np.asarray(args.wind_ned)
                plant.wind+=(wind-plant.wind)*(1-np.exp(-plant.dt/2))
                plant.step(command,armed)
                if step%5==0:
                    avatar.publish(plant,armed,step*plant.dt)
                    flags=';'.join(plant.support_flags)
                    writer.writerow([step*plant.dt,int(armed),*plant.x,*(plant.rotor*60/(2*np.pi)),*command,*plant.wrench,*plant.wind,flags])
                    if flags!=previous_flags:
                        print('MODEL SUPPORT:',flags or 'spinning calibration command range',flush=True)
                        previous_flags=flags
                if step%250==0:
                    stream.flush()
                    status=dict(time_s=step*plant.dt,wall_s=time.monotonic()-wall,position=plant.x[:3].tolist(),
                        hakoniwa_time_s=avatar.lib.hako_asset_get_worldtime()/1e6,
                        rpm=(plant.rotor*60/(2*np.pi)).tolist(),armed=armed,model=args.model,flags=plant.support_flags)
                    if assist:
                        assist_stream.flush()
                        status['assist']=dict(method=args.assist,velocity=assist.output_velocity.tolist(),
                            raw_velocity=assist.observer.v.tolist(),pilot_zero_count=assist.pilot_zero.count,
                            zero_bias=assist.pilot_zero.bias.tolist(),zero_button=assist.zero_button.status,
                            corrections=assist.observer.corrections,mode=assist.mode,status=assist.observer.skipped)
                    (args.output/'research-status.json').write_text(json.dumps(status))
                step+=1
                wait=wall+step*plant.dt-time.monotonic()
                if wait>0: time.sleep(wait)
        except Exception as exc:
            (args.output/'research-error.txt').write_text(str(exc))
            raise
        finally:
            link.close()
            battery.close()
            if assist: assist.close();assist_stream.close()

if __name__=='__main__': main()
