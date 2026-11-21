"""Read-only diagnostics of a simulator session; never feeds truth to control."""
import argparse
import csv
import json
from pathlib import Path
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('--session',type=Path,required=True)
args=parser.parse_args()
rows=list(csv.DictReader((args.session/'velocity-assist.csv').open()))
flight=np.genfromtxt(args.session/'research-flight.csv',delimiter=',',names=True,encoding='utf-8')
def column(k): return np.array([float(r[k]) for r in rows])
t=column('time_s')
estimated=np.column_stack([column('estimated_vn'),column('estimated_ve')])
truth=np.column_stack([column('true_vn'),column('true_ve')])
target=np.column_stack([column('target_vn'),column('target_ve')])
height=-np.interp(t,flight['time_s'],flight['x2'])
flying=height>.3
active=flying&(column('px4_mode')==6)
center=np.linalg.norm(target,axis=1)<.01
# Require one second of centered sticks; exclude startup before any correction.
settled=np.convolve(center.astype(int),np.ones(50,dtype=int),'full')[:len(center)]==50
settled &= active & (column('corrections')>0)
def rms(mask,array):
    return float(np.sqrt(np.mean(np.sum(array[mask]**2,axis=1)))) if mask.any() else None
summary=dict(session=str(args.session),samples=len(t),offboard_flight_s=float(active.sum()*.02),
    max_true_height_m=float(height.max()),corrections=int(column('corrections').max()),
    horizontal_velocity_error_rmse_m_s=rms(active,estimated-truth),
    centered_true_speed_rms_m_s=rms(settled,truth),
    centered_estimated_speed_rms_m_s=rms(settled,estimated),
    centered_samples=int(settled.sum()),
    final_armed=bool(flight['armed'][-1]),
    scope='Simulation integration diagnostic; not independent real-flight validation')
(args.session/'assist-verification.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
