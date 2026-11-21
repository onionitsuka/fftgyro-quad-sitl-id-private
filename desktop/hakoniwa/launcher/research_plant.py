"""Frozen research loads -> official Hakoniwa rigid-body accelerations, SI/NED/FRD."""
import ctypes as ct
import json
import os
from pathlib import Path
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('HAKO_DESKTOP_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(HERE / 'research_model'))
import simulate as sim

class StartupLoads(sim.Loads):
    def __init__(self, config, identified, route, density):
        super().__init__(config, identified, route)
        self.density_scale = density / self.cfg.rho

    def __call__(self, air, rate, rotor, rotor_dot):
        base = self.propulsion(rate, rotor, rotor_dot)
        # Rotor angular momentum does not scale with atmospheric density.
        aero_base = self.propulsion(np.zeros(3), rotor, np.zeros(4))
        gyro = base - aero_base
        # Every rotor appears in inflow denominators. Mean RPM is insufficient
        # when one motor stops before the others during touchdown.
        rpm = float(np.min(rotor) * 60 / (2*np.pi))
        correction = np.zeros(6)
        if self.identified and rpm > 3000:
            t = np.clip((rpm-3000)/500, 0, 1)
            correction = t*t*(3-2*t) * self.residual(air, rate, rotor, rotor_dot)
        return self.density_scale * (aero_base + correction) + gyro

class Plant:
    dt = .004
    def __init__(self, model='identified', route='command_route', voltage=16., density=None, roll_transfer=None):
        self.config = json.loads((HERE/'research_model/model.json').read_text())
        if roll_transfer is not None:
            self.config['roll_transfer'] = roll_transfer
        self.voltage = voltage
        self.density = self.config['settings']['rho'] if density is None else density
        self.vehicle = StartupLoads(self.config, model == 'identified', route, self.density)
        self.lib = ct.CDLL(str(ROOT/'lib/libphysics_bridge.so'))
        self.call = self.lib.hako_wrench_acceleration
        ptr = np.ctypeslib.ndpointer(dtype=np.float64, ndim=1, flags='C_CONTIGUOUS')
        self.call.argtypes = [ptr,ptr,ptr,ptr,ct.c_double,ptr,ct.c_double,ptr,ptr]
        self.call.restype = None
        self.x = np.zeros(13); self.x[6] = 1
        self.rotor = np.zeros(4); self.wind = np.zeros(3)
        self.force = np.array([0.,0.,-sim.G]); self.wrench = np.zeros(6)
        self.command = np.zeros(4); self.support_flags = []

    def derivative(self, x, rotor, rotor_dot):
        r = sim.rotation(x[6:10]); rate = np.ascontiguousarray(x[10:13])
        air = r.T @ (x[3:6]-self.wind)
        if np.linalg.norm(air) > self.config['airspeed_limit_m_s']:
            raise ValueError('対気速度11.5 m/s超: 研究モデルの適用範囲外')
        wrench = np.ascontiguousarray(self.vehicle(air, rate, rotor, rotor_dot))
        euler = np.array([np.arctan2(r[2,1],r[2,2]), np.arcsin(np.clip(-r[2,0],-1,1)), np.arctan2(r[1,0],r[0,0])])
        a, alpha = np.empty(3), np.empty(3)
        self.call(np.ascontiguousarray(r.T@x[3:6]), euler, rate, wrench,
                  self.vehicle.mass, np.ascontiguousarray(self.vehicle.inertia), sim.G, a, alpha)
        q = x[6:10]
        dq = .5*np.r_[-q[1:]@rate, q[0]*rate+np.cross(q[1:],rate)]
        return np.r_[x[3:6],a,dq,alpha], wrench

    def ground(self):
        r = sim.rotation(self.x[6:10]); yaw = np.arctan2(r[1,0],r[0,0])
        self.x[2:6] = 0
        self.x[6:10] = [np.cos(yaw/2),0,0,np.sin(yaw/2)]
        self.x[10:13] = 0

    def step(self, command, armed):
        self.command = np.clip(np.asarray(command),0,1)
        # Spinning-range map; zero command/Disarm is explicitly stopped.
        goal = np.maximum(0,sim.motor_speed(self.command,self.voltage,self.config)) if armed else np.zeros(4)
        goal[self.command <= 0] = 0
        tau = np.array([m['tau_up_s'] if goal[i]>=self.rotor[i] else m['tau_down_s'] for i,m in enumerate(self.config['motor_models'])])
        new = goal+(self.rotor-goal)*np.exp(-self.dt/tau)
        new[new<1e-8] = 0
        rotor = (new+self.rotor)/2; rotor_dot = (new-self.rotor)/self.dt
        oldv = self.x[3:6].copy()
        k1,self.wrench = self.derivative(self.x,rotor,rotor_dot)
        if self.x[2]>=0 and k1[5]>=0:
            self.ground()
        else:
            k2,self.wrench = self.derivative(self.x+k1*self.dt/2,rotor,rotor_dot)
            self.x += k2*self.dt
            self.x[6:10] /= np.linalg.norm(self.x[6:10])
            if self.x[2]>0: self.ground()
        self.force = sim.rotation(self.x[6:10]).T@((self.x[3:6]-oldv)/self.dt-[0,0,sim.G])
        self.rotor = new
        self.support_flags = []
        if armed and np.any((self.command<.30)|(self.command>.70)):
            self.support_flags.append('motor_command_outside_calibration')
        if np.min(new)*60/(2*np.pi)<3500:
            self.support_flags.append('startup_extension')
        if not np.isfinite(self.x).all() or np.linalg.norm(self.x[10:13])>30:
            raise ValueError('nonfinite state or angular-rate limit exceeded')
