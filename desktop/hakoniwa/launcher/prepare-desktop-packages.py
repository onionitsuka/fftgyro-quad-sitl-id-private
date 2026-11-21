"""Select desktop-required Meta packages; omit unsupported MR Utility Kit on Linux."""
import json
import os
from pathlib import Path

root = Path(os.environ.get('HAKO_DESKTOP_ROOT', Path(__file__).resolve().parents[1]))
p = root / 'hakoniwa-unity-drone/simulation/Packages/manifest.json'
data = json.loads(p.read_text())
deps = data['dependencies']
if 'com.meta.xr.sdk.all' in deps:
    backup = root / 'official-manifest-before-linux-desktop.json'
    if not backup.exists():
        backup.write_text(p.read_text())
    version = deps.pop('com.meta.xr.sdk.all')
    for name in ('core', 'audio', 'interaction', 'interaction.ovr'):
        deps['com.meta.xr.sdk.' + name] = version
    p.write_text(json.dumps(data, indent=2) + '\n')
    print('Selected desktop Meta packages, retained version', version)
