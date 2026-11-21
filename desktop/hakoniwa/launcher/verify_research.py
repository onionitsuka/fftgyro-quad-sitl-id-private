"""Offline equation equivalence and explicit loopback-only SITL maneuver check."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from research_plant import Plant, sim, ROOT

def equations():
    rng=np.random.default_rng(12); errors=[]; skipped=0
    for route in ('measured','command_route'):
        p=Plant(route=route)
        ref=sim.Loads(p.config,True,route)
        for _ in range(60):
            x=np.r_[np.zeros(3),rng.uniform(-3,3,3),sim.attitude(*rng.uniform(-.3,.3,2)),rng.uniform(-.5,.5,3)]
            rotor=rng.uniform(3800,5500,4)*2*np.pi/60
            dot=rng.uniform(-20,20,4)
            try:
                actual,w=p.derivative(x,rotor,dot)
                expected,we=sim.derivative(x,ref,rotor,dot,p.wind)
            except ValueError as exc:
                if 'Ambiguous' not in str(exc): raise
                skipped+=1; continue
            errors.append(max(np.max(np.abs(actual-expected)),np.max(np.abs(w-we))))
    if max(errors)>1e-10: raise AssertionError(max(errors))
    # FRD positive Fz acceleration; native C adapter includes gravity only once.
    p=Plant(model='existing'); p.x[2]=-2
    dx,w=p.derivative(p.x,np.zeros(4),np.zeros(4))
    assert abs(dx[5]-sim.G)<1e-12
    # Wind must be subtracted in world coordinates before the body transformation.
    p=Plant(); p.x[2]=-2; p.x[6:10]=sim.attitude(.2,-.1)
    p.x[3:6]=[2.,1.,0.]; p.wind=np.array([0.,-2.,0.])
    rotor=np.full(4,4500*2*np.pi/60); dot=np.zeros(4)
    _,w=p.derivative(p.x,rotor,dot)
    expected=p.vehicle(sim.rotation(p.x[6:10]).T@(p.x[3:6]-p.wind),p.x[10:13],rotor,dot)
    assert np.allclose(w,expected,rtol=0,atol=1e-12)
    # Density scales aerodynamic forces, but not rotor acceleration reaction.
    p=Plant(model='existing'); dense=Plant(model='existing',density=1.3)
    rate=np.array([.1,-.2,.3]); dot=np.array([1.,2.,3.,4.])
    base=p.vehicle.propulsion(np.zeros(3),rotor,np.zeros(4))
    gyro=p.vehicle.propulsion(rate,rotor,dot)-base
    assert np.allclose(dense.vehicle(np.zeros(3),rate,rotor,dot),base*1.3/1.225+gyro)
    p=Plant()
    rotor=np.array([0.,4500.,4500.,4500.])*2*np.pi/60
    w=p.vehicle(np.array([2.,0.,0.]),rate,rotor,dot)
    assert np.isfinite(w).all()
    assert np.allclose(w,p.vehicle.propulsion(rate,rotor,dot))
    return dict(states=len(errors),ambiguous_root_cases_skipped=skipped,max_equation_error=max(errors),freefall_z=dx[5],wind_frame_check=True,density_gyro_check=True,one_rotor_stopped_check=True)

def flight(multi_axis=False):
    from pymavlink import mavutil
    m=mavutil.mavlink
    link=mavutil.mavlink_connection('udpin:127.0.0.1:14549',source_system=254)
    hb=link.wait_heartbeat(timeout=12)
    if hb is None or hb.get_srcSystem()!=11:
        raise RuntimeError('Verification is restricted to local SITL instance 10 / system 11')
    target=11; values=[]; events=[]; mode=None; armed=False
    start=time.monotonic(); lastmanual=0; acted=set()
    # Land detection needs time after touchdown, especially with steady wind.
    while time.monotonic()-start<(120 if multi_axis else 75):
        t=time.monotonic()-start
        if t-lastmanual>.04:
            link.mav.heartbeat_send(m.MAV_TYPE_GCS,m.MAV_AUTOPILOT_INVALID,0,0,0)
            z=650 if 8<t<12 else 500
            x=250 if 20<t<24 else (-250 if 30<t<34 else 0)
            y=(150 if 38<t<42 else (-150 if 48<t<52 else 0)) if multi_axis else 0
            yaw=(50 if 56<t<60 else (-50 if 66<t<70 else 0)) if multi_axis else 0
            link.mav.manual_control_send(target,x,y,z,yaw,0)
            lastmanual=t
        for at,name in ((2,'position'),(4,'arm'),(76 if multi_axis else 42,'land')):
            if t>=at and name not in acted:
                if name=='position': link.mav.set_mode_send(target,m.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,3<<16)
                if name=='arm': link.mav.command_long_send(target,1,m.MAV_CMD_COMPONENT_ARM_DISARM,0,1,0,0,0,0,0,0)
                if name=='land': link.mav.command_long_send(target,1,m.MAV_CMD_NAV_LAND,0,0,0,0,float('nan'),float('nan'),float('nan'),float('nan'))
                acted.add(name)
        msg=link.recv_match(blocking=True,timeout=.01)
        if msg is None: continue
        if msg.get_type()=='HEARTBEAT':
            mode=mavutil.mode_string_v10(msg); armed=bool(msg.base_mode&m.MAV_MODE_FLAG_SAFETY_ARMED)
        if msg.get_type() in ('STATUSTEXT','COMMAND_ACK'): events.append(dict(wall_s=t,**msg.to_dict()))
        if msg.get_type()=='LOCAL_POSITION_NED': values.append(dict(wall_s=t,mode=mode,armed=armed,**msg.to_dict()))
        if msg.get_type()=='STATUSTEXT' and 'Disarmed by landing' in msg.text:
            break
    link.close()
    height=max(-v['z'] for v in values)
    landed=any('Disarmed by landing' in e.get('text','') for e in events)
    summary=dict(max_height_m=height,landed_and_disarmed=landed,samples=len(values))
    summary['passed']=height>.3 and landed
    return dict(summary=summary,samples=values,events=events)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--flight',action='store_true')
    parser.add_argument('--multi-axis',action='store_true')
    parser.add_argument('--label',default='flight'); args=parser.parse_args()
    if not args.label.replace('-','').replace('_','').isalnum(): parser.error('Invalid label')
    out=ROOT/'research-verification'; out.mkdir(exist_ok=True)
    result=equations(); print(result,flush=True)
    (out/'equations.json').write_text(json.dumps(result,indent=2))
    if args.flight:
        result=flight(args.multi_axis); (out/(args.label+'.json')).write_text(json.dumps(result,indent=2))
        print('Saved flight verification',out,result['summary'],flush=True)
        if not result['summary']['passed']: raise SystemExit('SITL flight verification failed; diagnostic saved')
