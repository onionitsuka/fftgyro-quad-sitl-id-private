"""Real local HTTP server: static assets, bad requests, stepping, reset, exports."""
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest


@pytest.fixture(scope='module')
def server():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    app = Path(__file__).parents[1] / 'sim' / 'appendix' / 'interactive.py'
    proc = subprocess.Popen([sys.executable, str(app), '--port', str(port), '--no-browser'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(150):
            try:
                with urlopen(base+'/state', timeout=1):
                    break
            except (URLError, TimeoutError):
                if proc.poll() is not None:
                    pytest.fail(proc.stdout.read().decode())
                time.sleep(.1)
        else:
            pytest.fail('Server did not start')
        yield base
    finally:
        proc.terminate()
        proc.communicate(timeout=10)


def request(base, path, body=None):
    req = Request(base+path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    with urlopen(req, timeout=10) as response:
        return response.read()


def test_assets_and_missing_paths(server):
    for path in ['/', '/assets/app.js', '/assets/style.css']:
        assert len(request(server,path)) > 100
    with pytest.raises(HTTPError) as error:
        request(server, '/assets/../../model.json')
    assert error.value.code == 404


def test_bad_json_shape_is_rejected_and_server_recovers(server):
    with pytest.raises(HTTPError) as error:
        request(server, '/step', [])
    assert error.value.code == 400
    assert json.loads(request(server,'/state'))['time'] >= 0


def test_simulate_reset_and_export(server):
    before = json.loads(request(server,'/state'))['time']
    after = json.loads(request(server,'/step',{'forward':.1}))
    assert after['time'] > before
    session=json.loads(request(server,'/session.json'))
    assert 'assets/app.js' in session['code_sha256']
    assert b'time_s' in request(server,'/trace.csv')
    reset=json.loads(request(server,'/reset',{'model':'existing','route':'measured'}))
    assert reset['time'] == 0 and reset['model'] == 'existing'
