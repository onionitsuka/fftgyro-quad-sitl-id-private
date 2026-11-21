"""Native Gazebo sensors, motor joints and rigid body with the saved research residual."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import xml.etree.ElementTree as ET
from build_native_gazebo_model import build
from parameters import common_parameters

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--px4-root',type=Path,required=True)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--model',choices=['identified','existing'],default='identified')
    p.add_argument('--route',choices=['measured','command_route'],default='command_route')
    p.add_argument('--headless',action='store_true')
    args=p.parse_args()
    here=Path(__file__).resolve().parent
    models=here.parent/'hakoniwa/launcher/research_model/model.json'
    artifact=json.loads(models.read_text())
    output=args.root/'sessions'/time.strftime('%Y%m%d-%H%M%S')
    output.mkdir(parents=True,exist_ok=False)
    variant=build(args.px4_root,artifact,output/'models')
    sdf=output/'models/fftgyro_x500/model.sdf'
    tree=ET.parse(sdf)
    plugin=ET.SubElement(tree.getroot().find('model'),'plugin',filename='gz-sim-python-system-loader-system',name='gz::sim::systems::PythonSystemLoader')
    for key,value in dict(module_name='gazebo_identified_system',coefficient_route=args.route if args.model=='identified' else 'baseline',models=str(models),output=str(output)).items():
        ET.SubElement(plugin,key).text=value
    tree.write(sdf,encoding='utf-8',xml_declaration=True)
    binary=args.px4_root/'build/px4_sitl_default/bin/px4'
    rootfs=output/'rootfs'; rootfs.mkdir()
    (rootfs/'etc').symlink_to(binary.parent.parent/'etc',target_is_directory=True)
    startup=output/'startup.sh'
    params=common_parameters(artifact)
    params.update(COM_RC_IN_MODE=1)
    startup.write_text('#!/bin/sh\n. etc/init.d-posix/rcS\n'+''.join(f'param set {k} {v}\n' for k,v in params.items()))
    simulation=args.px4_root/'Tools/simulation/gz'
    env=dict(os.environ,PX4_SYS_AUTOSTART='4001',PX4_SIM_MODEL='fftgyro_x500',PX4_GZ_MODEL_POSE=f'0,0,0,0,0,{math.pi/2}',
             PX4_GZ_STANDALONE='1',PX4_GZ_WORLD='default',PX4_GZ_NO_FOLLOW='1',GZ_IP='127.0.0.1',
             GZ_PARTITION='appendix_'+hashlib.sha256(str(output).encode()).hexdigest()[:12],
             GZ_SIM_RESOURCE_PATH=f'{output/"models"}:{simulation/"models"}:{simulation/"worlds"}',
             GZ_SIM_SYSTEM_PLUGIN_PATH=f'{binary.parent.parent/"src/modules/simulation/gz_plugins"}:{here}',
             GZ_SIM_SERVER_CONFIG_PATH=str(args.px4_root/'src/modules/simulation/gz_bridge/server.config'))
    # PythonSystemLoader embeds the system Python; make this venv's packages available.
    import site
    env['PYTHONPATH']=os.pathsep.join([str(here),*site.getsitepackages(),env.get('PYTHONPATH','')])
    (output/'manifest.json').write_text(json.dumps(dict(model=args.model,route=args.route,model_sha256=hashlib.sha256(models.read_bytes()).hexdigest(),native=variant,
        limitations=['Native Gazebo motor response retained; not the Hakoniwa command/voltage RPM model',
                     'Native rotor inertia/joints retained; rotor acceleration reaction is not replaced',
                     'No wind field in this packaged Gazebo scene; not a flight-validation result']),indent=2))
    children=[]; streams=[]
    def stop(*_): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        for name,cmd,cwd in [('gazebo',['gz','sim','-r',*(['-s'] if args.headless else []),str(simulation/'worlds/default.sdf')],output),
                             ('px4',[str(binary),'-d','-s',str(startup)],rootfs)]:
            f=(output/f'{name}.log').open('w');streams.append(f)
            children.append(subprocess.Popen(cmd,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True))
        print('Gazebo + PX4 started. Open QGroundControl. No automatic arming. Logs:',output,flush=True)
        started=time.monotonic()
        while all(c.poll() is None for c in children):
            if (output/'plugin_failure.json').exists(): raise RuntimeError((output/'plugin_failure.json').read_text())
            if time.monotonic()-started>60 and not (output/'plugin_ready.json').exists(): raise RuntimeError('Gazebo research plugin did not load; see logs')
            time.sleep(.5)
        raise RuntimeError('Simulator exited; see logs')
    except KeyboardInterrupt: pass
    finally:
        for c in reversed(children):
            if c.poll() is None: os.killpg(c.pid,signal.SIGTERM)
        for c in children:
            try:c.wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(c.pid,signal.SIGKILL);c.wait()
        for f in streams:f.close()
if __name__=='__main__':main()
