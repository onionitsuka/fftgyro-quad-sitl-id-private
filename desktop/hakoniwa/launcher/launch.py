"""Official Linux Avatar / Hakoniwa / PX4, all on one desktop. Simulation only."""
import ctypes
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import time

ROOT = Path(os.environ.get('HAKO_DESKTOP_ROOT', Path(__file__).resolve().parents[1]))
installation = json.loads((ROOT/'installation.json').read_text()) if (ROOT/'installation.json').exists() else {}
PX4 = Path(os.environ.get('HAKO_PX4_ROOT',installation.get('px4_root',''))) / 'build/px4_sitl_default'
PROJECT = ROOT / 'hakoniwa-unity-drone/simulation'
profile_path = ROOT / 'profile.json'
profile = json.loads(profile_path.read_text()) if profile_path.exists() else {'model':'official'}
profile['model'] = os.environ.get('HAKO_MODEL',profile.get('model','official'))
if 'HAKO_WIND_NED' in os.environ:
    profile['wind_ned'] = [float(v) for v in os.environ['HAKO_WIND_NED'].split(',')]
if 'HAKO_ASSIST' in os.environ:
    profile['assist']=os.environ['HAKO_ASSIST']
if profile['model'] not in ('official','identified','existing'):
    raise ValueError('Unknown simulator model')
instance = int(os.environ.get('HAKO_INSTANCE','8'))
headless = os.environ.get('HAKO_HEADLESS') == '1'
research = profile['model'] != 'official'
children, streams = [], []

def stop(*_):
    raise SystemExit(0)

def start(args, name, cwd=ROOT, env=None):
    f = (session / f'{name}.log').open('w')
    streams.append(f)
    p = subprocess.Popen(args, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT)
    children.append(p)
    return p

def wait_log(name, text, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        path = session / f'{name}.log'
        if path.exists() and text in path.read_text(errors='replace'):
            return
        if any(p.poll() is not None for p in children):
            raise RuntimeError(f'A process exited; see {session}')
        time.sleep(.2)
    raise TimeoutError(f'{name}: missing {text}; see {session}')

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
app = ROOT / 'Build/Hakoniwa.x86_64'
if not app.exists():
    raise SystemExit('Run build-avatar.sh after Unity Hub login and license activation.')
session = ROOT / 'sessions' / (time.strftime('%Y%m%d-%H%M%S') + f'-{profile["model"]}-{instance}')
(session / 'mmap').mkdir(parents=True)
config = session / 'cpp_core_config.json'
config.write_text(json.dumps({'shm_type': 'mmap', 'core_mmap_path': str(session / 'mmap')}))
env = dict(os.environ, HAKO_CONFIG_PATH=str(config))
rootfs = session / 'px4'
rootfs.mkdir()
shutil.copytree(PX4/'etc',rootfs/'etc',symlinks=True)
airframe = '900003'
if research:
    airframe = '900004'
    params = json.loads((ROOT/'launcher/research-parameters.json').read_text())
    params.update(CA_AIRFRAME=0,CA_ROTOR_COUNT=4,THR_MDL_FAC=.55)
    # The research plant uses a constant supply voltage. Publish that voltage
    # from its sensor loop, not PX4's independent time-draining battery model.
    params.update(SIM_BAT_DRAIN=0,BAT1_N_CELLS=4)
    mavlink_script=rootfs/'etc/init.d-posix/px4-rc.mavlink'
    with mavlink_script.open('a') as f:
        f.write(f'\nmavlink start -x -u {14900+instance} -o {15000+instance} -r 10000 -m custom\n')
    if profile.get('assist','none')!='none':
        params.update(EKF2_GPS_CTRL=0,EKF2_EV_CTRL=4,EKF2_BARO_CTRL=1,EKF2_HGT_REF=0,
                      EKF2_EV_NOISE_MD=0,COM_ARM_WO_GPS=1,COM_RC_OVERRIDE=0)
        mavlink_script=rootfs/'etc/init.d-posix/px4-rc.mavlink'
        with mavlink_script.open('a') as f:
            f.write(f'\nmavlink start -x -u {14700+instance} -o {14800+instance} -r 200000 -m onboard\n')
    for i in range(4):
        params.update({f'CA_ROTOR{i}_AX':0,f'CA_ROTOR{i}_AY':0,f'CA_ROTOR{i}_AZ':-1,
                       f'PWM_MAIN_FUNC{i+1}':101+i})
    body = '#!/bin/sh\n. ${R}etc/init.d/rc.mc_defaults\n'
    body += ''.join(f'param set-default {k} {v}\n' for k,v in params.items())
    (rootfs/'etc/init.d-posix/airframes/900004_research').write_text(body)
    (session/'px4-parameters.json').write_text(json.dumps(params,indent=2))
if headless:
    p=rootfs/'etc/init.d-posix/px4-rc.mavlink'
    p.write_text(p.read_text().replace('mavlink start -x -u $udp_gcs_port_local -r 4000000 -f',
                                     'mavlink start -x -u $udp_gcs_port_local -r 4000000 -f -o 14650'))
(session/'profile.json').write_text(json.dumps(profile,indent=2))
try:
    service_env = dict(env)
    transport_adapter = ROOT / 'lib/libsitl_tcp_nodelay.so'
    if not transport_adapter.exists():
        raise RuntimeError('Run prepare-runtime.sh to build the TCP transport adapter')
    service_env['LD_PRELOAD'] = str(transport_adapter)
    if research:
        python=Path(os.environ.get('HAKO_PYTHON',str(ROOT/'.venv/bin/python')))
        if not python.exists():
            raise RuntimeError('Set HAKO_PYTHON to a Python environment with requirements-research.txt installed')
        args=[str(python),str(ROOT/'launcher/research_backend.py'),'--model',profile['model'],
              '--route',profile.get('route','command_route'),'--voltage',str(profile.get('voltage',16)),
              '--port',str(4560+instance),'--output',str(session)]
        if 'density' in profile: args += ['--density',str(profile['density'])]
        if profile.get('direct_roll'): args += ['--direct-roll']
        args += ['--wind-ned',*[str(v) for v in profile.get('wind_ned',[0,0,0])]]
        args += ['--assist',profile.get('assist','none'),'--assist-port',str(14800+instance),'--system',str(instance+1)]
        args += ['--battery-port',str(14900+instance)]
        args += ['--accel-bias',*[str(v) for v in profile.get('accel_bias',[0,0,0])]]
        start(args,'service',ROOT,env)
        wait_log('service','RESEARCH READY')
    else:
        start([str(ROOT / 'runtime-v5.0.0/lnx/linux-main_hako_aircraft_service_px4'),
               '127.0.0.1',str(4560+instance),'config/drone/x500-px4-sitl',str(PROJECT/'avatar-drone.json')],
              'service',ROOT/'hakoniwa-drone-core',service_env)
        wait_log('service','wait for connection')
    start([str(PX4 / 'bin/px4'), '-i', str(instance), '-w',str(rootfs), '-d'], 'px4', rootfs,
          dict(env, PX4_SYS_AUTOSTART=airframe, PX4_SIM_MODEL='none_iris',
               PX4_SIM_HOSTNAME='127.0.0.1'))
    wait_log('service','PX4 research HIL connected' if research else 'WAIT START')
    start([str(app), '-screen-fullscreen', '0', '-screen-width', '1280',
           '-screen-height', '800', '-logFile', str(session / 'player.log')]+(['-batchmode','-nographics'] if headless else []),
          'player-process', PROJECT, env)
    wait_log('player', 'Register on Hakoniwa')
    os.environ['HAKO_CONFIG_PATH'] = str(config)
    lib = ctypes.CDLL(str(ROOT / 'lib/libshakoc.so'))
    lib.hako_simevent_init.restype = ctypes.c_bool
    lib.hako_simevent_start.restype = ctypes.c_bool
    if not lib.hako_simevent_init() or not lib.hako_simevent_start():
        raise RuntimeError('Hakoniwa start failed')
    print(f'Model: {profile["model"]}. Open QGroundControl. Logs: {session}', flush=True)
    while all(p.poll() is None for p in children):
        time.sleep(1)
    error_path=session/'research-error.txt'
    reason=error_path.read_text() if error_path.exists() else 'シミュレータのプロセスが終了しました。'
    message=f'{reason}\n「箱庭を再起動」で再開できます。\nログ: {session}'
    print(message,flush=True)
    if not headless and shutil.which('notify-send'):
        subprocess.run(['notify-send','箱庭シミュレータ',message],check=False,timeout=5)
finally:
    for p in reversed(children):
        if p.poll() is None:
            p.terminate()
    for p in children:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
    for f in streams:
        f.close()
