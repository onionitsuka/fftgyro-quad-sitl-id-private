"""Reject unsupported platforms/options instead of silently starting the browser demo."""
import importlib.util
from pathlib import Path
import sys
import pytest

spec=importlib.util.spec_from_file_location('desktop_entry',Path(__file__).parents[1]/'desktop.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)

def test_desktop_does_not_fall_back_to_browser_on_mac(monkeypatch,capsys):
    monkeypatch.setattr(entry.platform,'system',lambda:'Darwin')
    monkeypatch.setattr(sys,'argv',['desktop.py','launch','hakoniwa'])
    with pytest.raises(SystemExit) as e:entry.main()
    assert e.value.code==2
    assert 'requires x86_64 Ubuntu' in capsys.readouterr().err

def test_gazebo_rejects_unimplemented_wind(monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['desktop.py','launch','gazebo','--wind-ned','1','0','0'])
    with pytest.raises(SystemExit) as e:entry.main()
    assert e.value.code==2
    assert 'Hakoniwa only' in capsys.readouterr().err
