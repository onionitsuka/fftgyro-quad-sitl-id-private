"""Check callback clock and failure handling without requiring Gazebo locally."""
import importlib.util
import sys
import types
import copy
import pytest
from datetime import timedelta
from pathlib import Path


def load_system(monkeypatch):
    for name, attributes in [("gz",{}),("gz.math7",{"Vector3d":object}),
                             ("gz.sim8",{"Link":object,"Model":object})]:
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules,name,module)
    scripts = Path(__file__).parents[1]/"desktop"/"gazebo"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("test_native_system",scripts/"gazebo_identified_system.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    system = module.IdentifiedSystem()
    system.failed,system.last_time = False,None
    return system


def test_no_duplicate_or_zero_dt_wrench(monkeypatch):
    system = load_system(monkeypatch)
    calls = []
    assert not hasattr(system,"update")
    system.apply_step = lambda info,ecm: calls.append(info.sim_time)
    def step(time,dt,paused=False):
        system.pre_update(types.SimpleNamespace(sim_time=timedelta(seconds=time),
            dt=timedelta(seconds=dt),paused=paused),None)
    step(1,0)
    step(1,.004)
    step(1,.004)
    step(1.004,.004,True)
    step(1.004,.004)
    assert calls == [timedelta(seconds=1),timedelta(seconds=1.004)]


def test_model_failure_writes_marker_and_stops_application(monkeypatch,tmp_path):
    system = load_system(monkeypatch)
    system.output = tmp_path
    system.stream = types.SimpleNamespace(flush=lambda:None)
    def fail(info,ecm):
        raise ValueError("unsupported inflow")
    system.apply_step = fail
    info = types.SimpleNamespace(sim_time=timedelta(seconds=1),dt=timedelta(seconds=.004),paused=False)
    system.pre_update(info,None)
    assert system.failed
    assert "unsupported inflow" in (tmp_path/"plugin_failure.json").read_text()
