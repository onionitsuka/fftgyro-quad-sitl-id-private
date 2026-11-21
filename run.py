#!/usr/bin/env python3
"""Cross-platform entry point; bootstrap uses Python's standard library only."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parent
APP = ROOT / 'sim' / 'appendix'
ENV = ROOT / '.venv'


def env_python(root=ENV):
    return root / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def execute(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def setup(dev=False):
    if sys.version_info < (3, 11):
        raise RuntimeError('Python 3.11以上をインストールしてください。')
    if not env_python().exists():
        print('専用のPython環境を作成しています…', flush=True)
        venv.EnvBuilder(with_pip=True).create(ENV)
    req = APP / ('requirements-dev.txt' if dev else 'requirements.txt')
    execute([env_python(), '-m', 'pip', 'install', '-r', req])
    execute([env_python(), '-c', 'import numpy, scipy, matplotlib; import matplotlib.pyplot'])
    (ENV / '.ready').write_text((APP / 'requirements.txt').read_text(), encoding='utf-8')
    print('導入完了。次回からランチャーで起動できます。', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='付録Cシミュレータ：初回導入・操縦・比較計算')
    parser.add_argument('action', nargs='?', default='interactive', choices=['setup', 'interactive', 'batch', 'test', 'doctor'])
    parser.add_argument('--dev', action='store_true', help='テスト用パッケージも導入（setup用）')
    args, extra = parser.parse_known_args(argv)
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / '.cache' / 'matplotlib'))
    if args.action == 'setup':
        setup(args.dev)
        return 0
    if args.action == 'doctor':
        print('Python:', sys.version.split()[0], '\nProject:', ROOT, '\nEnvironment:', env_python())
        if not env_python().exists():
            print('未導入です。python run.py setup を実行してください。')
            return 1
        execute([env_python(), '-c', 'import sys, numpy, scipy, matplotlib; import matplotlib.pyplot; print(sys.version); print("numpy", numpy.__version__, "scipy", scipy.__version__, "matplotlib", matplotlib.__version__)'])
        return 0
    ready = ENV / '.ready'
    if not env_python().exists() or not ready.exists() or ready.read_text(encoding='utf-8') != (APP / 'requirements.txt').read_text():
        setup(dev=args.action == 'test')
    if args.action == 'test':
        # Explicit test command may add test-only dependencies to the private venv.
        execute([env_python(), '-m', 'pip', 'install', '-r', APP / 'requirements-dev.txt'])
        execute([env_python(), '-m', 'pytest', str(APP / 'tests'), str(ROOT / 'tests'), *extra], cwd=ROOT)
    else:
        script = 'interactive.py' if args.action == 'interactive' else 'simulate.py'
        if args.action == 'batch' and not extra:
            from datetime import datetime
            extra = ['--output', str(ROOT / 'results' / datetime.now().strftime('%Y%m%d-%H%M%S-%f'))]
        execute([env_python(), APP / script, *extra], cwd=ROOT)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\n終了しました。')
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'\n実行できませんでした: {error}\n導入失敗時はネット接続を確認し、python run.py setup を再実行してください。', file=sys.stderr)
        raise SystemExit(1)
