"""Restart only this desktop SITL session; preserve QGC and all session logs."""
import fcntl
import os
from pathlib import Path
import signal
import time

root = Path(os.environ.get('HAKO_DESKTOP_ROOT', Path(__file__).resolve().parents[1]))
launcher = root / 'launcher/launch.py'
lock = (root / 'restart.lock').open('w')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
targets = []
for p in Path('/proc').iterdir():
    if not p.name.isdigit():
        continue
    try:
        args = (p / 'cmdline').read_bytes().split(b'\0')
        if len(args) > 1 and args[1] == os.fsencode(launcher):
            targets.append(int(p.name))
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        pass
for pid in targets:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
deadline = time.monotonic() + 25
while targets and time.monotonic() < deadline:
    alive = []
    for pid in targets:
        try:
            state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
            if state != 'Z':
                alive.append(pid)
        except FileNotFoundError:
            pass
    targets = alive
    if targets:
        time.sleep(.2)
if targets:
    raise SystemExit(f'Previous simulator is still shutting down: {targets}')
print('Starting a new simulator session; QGC calibration and old logs are preserved.', flush=True)
os.execv('/bin/bash', ['bash', str(root / 'launcher/launch.sh')])
