"""Install model and velocity-assist choices in the Ubuntu application menu."""
from pathlib import Path
import os
root=Path(os.environ.get('HAKO_DESKTOP_ROOT',Path(__file__).resolve().parents[1]))
dest=Path.home()/'.local/share/applications'; dest.mkdir(parents=True,exist_ok=True)
for model,label in [('identified','箱庭・研究モデル'),('existing','箱庭・回転数二乗モデル'),('official','箱庭・公式X500')]:
    (dest/f'hakoniwa-{model}.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName='+label+'\nExec=python3 '+str(root/'launcher/select-model.py')+' '+model+
        '\nTerminal=true\nCategories=Science;\n')
for mode,label in [('aero','箱庭・推定速度アシスト'),('imu','箱庭・IMU積分アシスト（比較用）')]:
    (dest/f'hakoniwa-assist-{mode}.desktop').write_text(
        '[Desktop Entry]\nType=Application\nName='+label+'\nExec=python3 '+str(root/'launcher/select-model.py')+
        ' identified --assist '+mode+'\nTerminal=true\nCategories=Science;\n')
