"""Pilot-declared horizontal zero speed; no navigation truth is accepted."""
import os
from pathlib import Path
import struct
import numpy as np


class PilotZero:
    def __init__(self):
        self.bias=np.zeros(2)
        self.count=0
        self.reset_counter=0

    def apply(self,velocity,request=False,ground=False):
        velocity=np.asarray(velocity,float).copy()
        if ground:
            if np.any(self.bias): self.reset_counter=(self.reset_counter+1)%256
            self.bias[:]=0
        elif request:
            self.bias[:]=velocity[:2]
            self.count+=1
            self.reset_counter=(self.reset_counter+1)%256
        velocity[:2]-=self.bias
        return velocity


class PilotZeroButton:
    """Read an unused InterLink button alongside QGC, without grabbing it.

    Linux joystick button 0; initial/held/reconnect events never trigger a zero.
    Only a fresh press after release is accepted. No axes are read or changed.
    """
    device=Path('/dev/input/by-id/usb-Spektrum_InterLinkDX_206337515242-joystick')

    def __init__(self,enabled=True):
        self.enabled=enabled
        self.fd=None
        self.released=False
        self.status='disconnected' if enabled else 'disabled'

    def poll(self):
        if not self.enabled: return False
        if self.fd is None:
            try:
                self.fd=os.open(self.device,os.O_RDONLY|os.O_NONBLOCK)
                self.status='connected'
                self.released=False
            except OSError: return False
        pressed=False
        try:
            while True:
                packet=os.read(self.fd,8)
                if len(packet)!=8: raise OSError('Joystick disconnected')
                _,value,kind,number=struct.unpack('<IhBB',packet)
                if kind&1 and number==0:
                    if kind&128:
                        self.released=value==0
                    elif value==0:
                        self.released=True
                    else:
                        pressed=pressed or self.released
                        self.released=False
        except BlockingIOError: pass
        except OSError:
            self.close()
            self.status='disconnected'
        return pressed

    def close(self):
        if self.fd is not None: os.close(self.fd)
        self.fd=None
        self.released=False
