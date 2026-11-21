"""Read-only check of the live Hakoniwa clock and Unity-produced LiDAR pose.

PX4 motion alone does not establish that Unity consumes the research pose.
Channel 17 is written by the official Unity LiDAR component after EventTick.
"""
import argparse
import ctypes as c
import json
import math
import os
from pathlib import Path
import struct
import time

parser=argparse.ArgumentParser()
parser.add_argument('--session',type=Path,required=True)
args=parser.parse_args()
root=Path(os.environ.get('HAKO_DESKTOP_ROOT',Path(__file__).resolve().parents[1]))
os.environ['HAKO_CONFIG_PATH']=str(args.session/'cpp_core_config.json')
lib=c.CDLL(str(root/'lib/libshakoc.so'))
lib.hako_asset_init.restype=c.c_bool
lib.hako_asset_get_worldtime.restype=c.c_longlong
lib.hako_asset_read_pdu_nolock.argtypes=[c.c_char_p,c.c_int,c.c_void_p,c.c_size_t]
lib.hako_asset_read_pdu_nolock.restype=c.c_bool
assert lib.hako_asset_init(), 'Cannot attach to Hakoniwa'

samples=[]
for _ in range(6):
    row={'world_s':lib.hako_asset_get_worldtime()/1e6}
    for channel,name in [(1,'plant_pose'),(17,'unity_lidar_pose')]:
        buf=c.create_string_buffer(72)
        assert lib.hako_asset_read_pdu_nolock(b'Drone',channel,buf,72), name
        assert struct.unpack_from('<I',buf.raw)[0]==0x12345678, f'{name} was not published'
        row[name]=struct.unpack_from('<6d',buf.raw,24)
        assert all(math.isfinite(v) for v in row[name]), name
    row['position_separation_m']=math.dist(row['plant_pose'][:3],row['unity_lidar_pose'][:3])
    samples.append(row)
    time.sleep(.4)
clock_advance=samples[-1]['world_s']-samples[0]['world_s']
largest_separation=max(s['position_separation_m'] for s in samples)
# Different origins (body / LiDAR) and one rendered frame of latency are expected.
passed=clock_advance>.1 and largest_separation<.5
result=dict(passed=passed,clock_advance_s=clock_advance,
            max_body_lidar_separation_m=largest_separation,samples=samples,
            scope='Unity-written pose and clock, not visual screenshot verification')
(args.session/'avatar-verification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='samples'},indent=2))
if not passed: raise SystemExit('Unity clock/pose verification failed')
