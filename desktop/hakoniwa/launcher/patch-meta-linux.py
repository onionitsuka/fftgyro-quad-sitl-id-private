"""Guard Meta XR 71's platform-specific Inspector UI on Linux; no runtime changes."""
import os
from pathlib import Path

root = Path(os.environ.get('HAKO_DESKTOP_ROOT', Path(__file__).resolve().parents[1]))
files = list((root / 'hakoniwa-unity-drone/simulation/Library/PackageCache').glob(
    'com.meta.xr.sdk.core@*/Scripts/Editor/OVRManagerEditor.cs'))
if len(files) != 1:
    raise SystemExit('Expected one installed Meta XR core package')
p = files[0]
text = p.read_text()
marker = '// Local Linux fix: mirror the platform guard for the manager variable.'
if marker in text:
    raise SystemExit(0)
start = text.index('        #region DynamicResolution')
end = text.index('        #endregion', start) + len('        #endregion')
block = text[start:end]
if 'ref manager.enableDynamicResolution' not in block:
    raise SystemExit('Unexpected Meta XR source; inspect before patching')
(root / 'OVRManagerEditor.cs.before-linux-fix').write_text(text)
guard = '#if UNITY_EDITOR_WIN || UNITY_STANDALONE_WIN || UNITY_EDITOR_OSX || UNITY_STANDALONE_OSX || UNITY_ANDROID'
p.write_text(text[:start] + marker + '\n' + guard + '\n' + block + '\n#endif' + text[end:])
print('Applied Linux-only Editor UI guard:', p)
