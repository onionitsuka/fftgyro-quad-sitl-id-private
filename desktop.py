#!/usr/bin/env python3
"""Install and run the PX4 desktop simulators, independently of the browser demo."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import urllib.request
import venv
import zipfile

os.environ["PYTHONNOUSERSITE"] = "1"
REPO = Path(__file__).resolve().parent
LOCK = json.loads((REPO/'desktop/sources.json').read_text())

def run(args, **kwargs):
    print('+', ' '.join(map(str,args)), flush=True)
    subprocess.run(list(map(str,args)), check=True, **kwargs)

def source(name, destination, reuse=None):
    spec = LOCK[name]
    if not destination.exists():
        if reuse and reuse.exists():
            # Shared source objects, but a separate checkout: never patch the old installation.
            run(['git','clone','--shared',reuse,destination])
        else:
            run(['git','clone',spec['url'],destination])
        run(['git','-C',destination,'checkout','--detach',spec['revision']])
    actual = subprocess.check_output(['git','-C',destination,'rev-parse','HEAD'],text=True).strip()
    if actual != spec['revision']:
        raise RuntimeError(f'{destination}: expected {spec["revision"]}, got {actual}; use a new --root')
    run(['git','-C',destination,'submodule','update','--init','--recursive'])

def python_env(root, requirements):
    python=root/'.venv/bin/python'
    if not python.exists(): venv.EnvBuilder(with_pip=True,system_site_packages=True).create(root/'.venv')
    run([python,'-m','pip','install','-r',requirements])
    return python

def setup(args, root):
    if sys.version_info < (3,12): raise RuntimeError('Desktop setup requires Python 3.12 or newer')
    root.mkdir(parents=True,exist_ok=True)
    old = args.reuse_hakoniwa.resolve() if args.reuse_hakoniwa else None
    px4 = args.px4_root.resolve() if args.px4_root else root/'PX4-Autopilot'
    if not args.px4_root:
        source('px4_'+args.backend,px4)
        # OS dependencies are installed with the documented PX4 official setup script.
        build_python = root/'.px4-build-env/bin/python'
        if not build_python.exists(): venv.EnvBuilder(with_pip=True).create(root/'.px4-build-env')
        run([build_python,'-m','pip','install','-r',px4/'Tools/setup/requirements.txt'])
        build_env=dict(os.environ,PATH=str(build_python.parent)+os.pathsep+os.environ['PATH'])
        run(['make','px4_sitl_default'],cwd=px4,env=build_env)
    binary=px4/'build/px4_sitl_default/bin/px4'
    if not binary.exists(): raise RuntimeError(f'PX4 is not built: {binary}')
    revision=subprocess.check_output(['git','-C',px4,'rev-parse','HEAD'],text=True).strip()
    if revision!=LOCK['px4_'+args.backend]['revision']:
        raise RuntimeError('PX4 revision differs from desktop/sources.json')
    if args.backend=='gazebo':
        python=python_env(root,REPO/'desktop/gazebo/requirements.txt')
        run([python,'-c','from gz.sim8 import Model; from gz.math7 import Vector3d'])
        run(['gz','sim','--version'])
    else:
        launcher=root/'launcher'
        shutil.copytree(REPO/'desktop/hakoniwa/launcher',launcher,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
        python=python_env(root,launcher/'requirements-research.txt')
        for name in ('hakoniwa-core-pro','hakoniwa-drone-core','hakoniwa-unity-drone'):
            source(name,root/name,old/name if old else None)
        runtime=root/'runtime-v5.0.0'
        if not (runtime/'lnx/libdrone_physics.a').exists():
            archive=root/'lnx.zip'
            if old and (old/'lnx.zip').exists(): shutil.copy2(old/'lnx.zip',archive)
            else: urllib.request.urlretrieve(LOCK['runtime']['url'],archive)
            if hashlib.sha256(archive.read_bytes()).hexdigest()!=LOCK['runtime']['sha256']:
                raise RuntimeError('Runtime archive checksum mismatch')
            with zipfile.ZipFile(archive) as z:
                for item in z.infolist():
                    if not (runtime/item.filename).resolve().is_relative_to(runtime.resolve()):
                        raise RuntimeError('Invalid archive path')
                z.extractall(runtime)
            for executable in (runtime/'lnx').glob('linux-*'): executable.chmod(0o755)
        (root/'lib').mkdir(exist_ok=True)
        (root/'cpp_core_config.json').write_text(json.dumps({'shm_type':'mmap','core_mmap_path':str(root/'mmap')}))
        env=dict(os.environ,HAKO_DESKTOP_ROOT=str(root),HAKO_PYTHON=str(python),HAKO_PX4_ROOT=str(px4))
        run(['bash',launcher/'prepare-runtime.sh'],env=env)
        run(['bash',launcher/'build-research.sh'],env=env)
        if args.avatar_build:
            # Copy a user-built Avatar, never a licensed binary into Git.
            shutil.copytree(args.avatar_build,root/'Build',dirs_exist_ok=True)
            shutil.copy2((root/'lib/libshakoc.so').resolve(),root/'Build/Hakoniwa_Data/Plugins/libshakoc.so')
        else:
            if args.unity_editor: env['UNITY_EDITOR']=str(args.unity_editor.resolve())
            run(['bash',launcher/'build-avatar.sh'],env=env)
        (root/'profile.json').write_text(json.dumps({'model':'identified','route':'command_route','assist':'none'}))
    config={'backend':args.backend,'px4_root':str(px4),'px4_revision':revision,'python':str(python),'repository':str(REPO)}
    (root/'installation.json').write_text(json.dumps(config,indent=2)+'\n')
    print('Installed:',root)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['setup','doctor','launch'])
    p.add_argument('backend',choices=['hakoniwa','gazebo'])
    p.add_argument('--root',type=Path)
    p.add_argument('--px4-root',type=Path)
    p.add_argument('--reuse-hakoniwa',type=Path,help='Reuse Git object cache and checked runtime archive')
    p.add_argument('--avatar-build',type=Path,help='Copy an already licensed/built Linux Avatar')
    p.add_argument('--unity-editor',type=Path)
    p.add_argument('--headless',action='store_true')
    p.add_argument('--model',choices=['identified','existing'],default='identified')
    p.add_argument('--route',choices=['measured','command_route'],default='command_route')
    p.add_argument('--assist',choices=['none','aero','imu'],default='none')
    p.add_argument('--instance',type=int,default=8)
    p.add_argument('--voltage',type=float,default=16.)
    p.add_argument('--wind-ned',type=float,nargs=3,default=[0.,0.,0.])
    p.add_argument('--accel-bias',type=float,nargs=3,default=[0.,0.,0.])
    p.add_argument('--direct-roll',action='store_true')
    args=p.parse_args()
    if not 0<=args.instance<=9: p.error('instance must be 0..9')
    if not 14.07<=args.voltage<=16.36: p.error('voltage must be 14.07..16.36 V')
    if not all(math.isfinite(v) for v in args.wind_ned+args.accel_bias): p.error('inputs must be finite')
    if sum(v*v for v in args.wind_ned)>100: p.error('wind magnitude must be at most 10 m/s')
    if args.backend=='gazebo' and (any(args.wind_ned) or any(args.accel_bias) or args.direct_roll or args.voltage != 16.):
        p.error('wind, IMU bias, voltage and direct Roll options are implemented in Hakoniwa only')
    if platform.system()!='Linux' or platform.machine() not in ('x86_64','AMD64'):
        p.error('This desktop package requires x86_64 Ubuntu. See docs/desktop-install.md for Mac/Windows.')
    root=(args.root or REPO/'.desktop-runtime'/args.backend).resolve()
    if args.action=='setup': setup(args,root); return
    config=json.loads((root/'installation.json').read_text())
    if args.action=='doctor':
        for path in (Path(config['python']),Path(config['px4_root'])/'build/px4_sitl_default/bin/px4'):
            if not path.exists(): raise RuntimeError(f'Missing: {path}')
        if args.backend=='hakoniwa':
            for name in ('Build/Hakoniwa.x86_64','lib/libphysics_bridge.so','lib/libshakoc.so'):
                if not (root/name).exists(): raise RuntimeError(f'Missing: {root/name}')
        else: run([config['python'],'-c','from gz.sim8 import Model'])
        print(json.dumps(config,indent=2)); return
    if args.backend=='hakoniwa':
        env=dict(os.environ,HAKO_DESKTOP_ROOT=str(root),HAKO_PX4_ROOT=config['px4_root'],HAKO_PYTHON=config['python'],
                 HAKO_MODEL=args.model,HAKO_ASSIST=args.assist,HAKO_INSTANCE=str(args.instance),HAKO_HEADLESS='1' if args.headless else '0')
        profile=json.loads((root/'profile.json').read_text());profile.update(route=args.route,voltage=args.voltage,wind_ned=args.wind_ned,accel_bias=args.accel_bias,direct_roll=args.direct_roll)
        (root/'profile.json').write_text(json.dumps(profile))
        os.execvpe('bash',['bash',str(root/'launcher/launch.sh')],env)
    else:
        if args.assist!='none': p.error('Velocity assist is implemented in Hakoniwa only')
        command=[config['python'],str(REPO/'desktop/gazebo/launch.py'),'--px4-root',config['px4_root'],
                 '--root',str(root),'--model',args.model,'--route',args.route]
        if args.headless: command+=['--headless']
        os.execv(config['python'],command)

if __name__=='__main__':
    try: main()
    except (OSError,RuntimeError,subprocess.CalledProcessError) as e:
        print(f'導入・起動に失敗しました: {e}',file=sys.stderr);sys.exit(1)
