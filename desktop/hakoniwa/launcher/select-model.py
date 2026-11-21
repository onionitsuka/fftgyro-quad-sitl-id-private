"""Choose a persisted simulation profile and restart this local simulator."""
import argparse
import json
import os
import math
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('model',choices=['official','identified','existing'])
parser.add_argument('--route',choices=['command_route','measured'],default='command_route')
parser.add_argument('--voltage',type=float,default=16.)
parser.add_argument('--density',type=float,default=1.225)
parser.add_argument('--direct-roll',action='store_true')
parser.add_argument('--wind-ned',type=float,nargs=3,default=[0.,0.,0.],metavar=('N','E','D'))
parser.add_argument('--assist',choices=['none','aero','imu'],default='none')
parser.add_argument('--accel-bias',type=float,nargs=3,default=[0.,0.,0.])
args=parser.parse_args()
if not 14.07<=args.voltage<=16.36: parser.error('Voltage must be 14.07..16.36 V')
if not 1.0<=args.density<=1.4: parser.error('Density must be 1.0..1.4 kg/m3')
if not sum(v*v for v in args.wind_ned)<=100: parser.error('Wind magnitude must be at most 10 m/s')
if args.model=='official' and args.assist!='none': parser.error('Assist requires research backend')
if not all(math.isfinite(v) for v in args.accel_bias): parser.error('IMU bias must be finite')
root=Path(os.environ.get('HAKO_DESKTOP_ROOT',Path(__file__).resolve().parents[1]))
profile=dict(model=args.model,route=args.route,voltage=args.voltage,density=args.density,direct_roll=args.direct_roll,wind_ned=args.wind_ned)
profile.update(assist=args.assist,accel_bias=args.accel_bias)
temp=root/'profile.new.json'; temp.write_text(json.dumps(profile,indent=2)); temp.replace(root/'profile.json')
print('Selected:',json.dumps(profile),flush=True)
os.execv('/bin/bash',['bash',str(root/'launcher/restart.sh')])
