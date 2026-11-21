import os
"""Two takeoff/landing cycles without restart, restricted to SITL instance 10."""
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from verify_research import flight, ROOT

binary=Path(os.environ['HAKO_PX4_ROOT'])/'build/px4_sitl_default/bin/px4-listener'
results=[]
out=ROOT/'research-verification/rearm.json'
session=max((ROOT/'sessions').glob('*-10'),key=lambda p:p.stat().st_mtime)
for cycle in range(2):
    result=flight()
    health={}
    for topic in ('battery_status','system_power'):
        text=subprocess.run([str(binary),'--instance','10',topic,'-n','1'],capture_output=True,text=True,timeout=5,check=True).stdout
        match=re.search(r'timestamp: (\d+) \(([\d.]+) seconds ago\)',text)
        health[topic]=dict(timestamp=int(match[1]),age_s=float(match[2])) if match else dict(error=text)
    result['periodic_health']=health
    data=np.genfromtxt(session/'research-flight.csv',delimiter=',',names=True,encoding='utf-8')
    armed=data['armed']>0
    starts=np.where(armed&~np.r_[False,armed[:-1]])[0]
    ends=np.where(armed&~np.r_[armed[1:],False])[0]
    if len(starts)!=cycle+1 or len(ends)!=len(starts):
        raise RuntimeError('Missing actual arm cycle in plant log')
    s,e=starts[-1],ends[-1]
    result['summary']['max_true_height_m']=float(-min(data['x2'][s:e+1]))
    result['summary']['passed'] &= result['summary']['max_true_height_m']>.3
    result['summary']['passed'] &= all(x.get('age_s',999)<1 for x in health.values())
    results.append(result)
    out.write_text(json.dumps(results,indent=2))
    print('Cycle',cycle+1,result['summary'],health,flush=True)
    if not result['summary']['passed']: raise SystemExit('Repeated-flight check failed; see '+str(out))
print('Both flights and periodic health updates passed without restart.',flush=True)
