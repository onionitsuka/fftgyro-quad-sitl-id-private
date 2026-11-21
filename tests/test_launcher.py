"""Installer behavior and portable paths without network access."""
import importlib.util
from pathlib import Path
import subprocess
import sys

spec = importlib.util.spec_from_file_location('launcher', Path(__file__).parents[1] / 'run.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_environment_path_with_spaces(tmp_path):
    root = tmp_path / 'folder with spaces'
    assert launcher.env_python(root).is_relative_to(root)


def test_help_without_dependencies():
    result = subprocess.run([sys.executable, str(launcher.ROOT / 'run.py'), '--help'], capture_output=True)
    assert result.returncode == 0
    assert b'interactive' in result.stdout


def test_setup_marks_ready_only_after_install(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, 'ENV', tmp_path)
    monkeypatch.setattr(launcher, 'env_python', lambda: Path(sys.executable))
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, 'pip')
    monkeypatch.setattr(launcher, 'execute', fail)
    import pytest
    with pytest.raises(subprocess.CalledProcessError):
        launcher.setup()
    assert not (tmp_path / '.ready').exists()
