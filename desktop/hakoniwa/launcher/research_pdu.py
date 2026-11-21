"""Official Hakoniwa shared-memory protocol adapter for the Avatar scene."""
import ctypes as c
import json
from pathlib import Path
import struct
import numpy as np

class Avatar:
    name = b'ResearchPlant'
    robot = b'Drone'
    def __init__(self,root):
        self.lib = c.CDLL(str(root/'lib/libshakoc.so'))
        signatures = {
            'hako_master_init':([],c.c_bool),
            'hako_master_execute':([],c.c_bool),
            'hako_master_set_config_simtime':([c.c_longlong,c.c_longlong],None),
            'hako_asset_init':([],c.c_bool),
            'hako_asset_register_polling':([c.c_char_p],c.c_bool),
            'hako_asset_get_event':([c.c_char_p],c.c_int),
            'hako_asset_notify_simtime':([c.c_char_p,c.c_longlong],None),
            'hako_asset_get_worldtime':([],c.c_longlong),
            'hako_asset_is_pdu_sync_mode':([c.c_char_p],c.c_bool),
            'hako_asset_notify_write_pdu_done':([c.c_char_p],None),
            'hako_simevent_get_state':([],c.c_int),
            'hako_simevent_init':([],c.c_bool),
            'hako_asset_create_pdu_lchannel':([c.c_char_p,c.c_int,c.c_uint],c.c_bool),
            'hako_asset_write_pdu':([c.c_char_p,c.c_char_p,c.c_int,c.c_void_p,c.c_uint],c.c_bool),
            'hako_asset_read_pdu':([c.c_char_p,c.c_char_p,c.c_int,c.c_void_p,c.c_uint],c.c_bool),
        }
        for key in ('start','stop','reset'):
            signatures['hako_asset_'+key+'_feedback'] = ([c.c_char_p,c.c_bool],c.c_bool)
        for name,(args,ret) in signatures.items():
            f=getattr(self.lib,name); f.argtypes=args; f.restype=ret
        if not self.lib.hako_master_init(): raise RuntimeError('Hakoniwa master init failed')
        self.lib.hako_master_set_config_simtime(100000,4000)
        if not self.lib.hako_asset_init() or not self.lib.hako_asset_register_polling(self.name):
            raise RuntimeError('Hakoniwa research asset registration failed')
        self.lib.hako_simevent_init()
        config=json.loads((root/'hakoniwa-unity-drone/simulation/avatar-drone.json').read_text())
        self.channels={}
        for robot in config['robots']:
            for key in ('shm_pdu_readers','shm_pdu_writers'):
                for pdu in robot.get(key,[]):
                    channel,size=pdu['channel_id'],pdu['pdu_size']
                    if channel not in self.channels:
                        if not self.lib.hako_asset_create_pdu_lchannel(self.robot,channel,size):
                            raise RuntimeError(f'Cannot declare channel {channel}')
                        self.channels[channel]=size

    def poll(self,t):
        self.lib.hako_asset_notify_simtime(self.name,round(t*1e6))
        for _ in range(8): self.advance_master()
        ev=self.lib.hako_asset_get_event(self.name)
        if ev in (1,2,3):
            key={1:'start',2:'stop',3:'reset'}[ev]
            getattr(self.lib,'hako_asset_'+key+'_feedback')(self.name,True)
        for _ in range(8): self.advance_master()
        return self.lib.hako_simevent_get_state()

    def advance_master(self):
        # PDU writes alone do not finish the asset's synchronization phase.
        # Without this acknowledgement, world time stays at zero and Unity's
        # EventTick/Physics.Simulate never run even though PX4 keeps flying.
        if self.lib.hako_asset_is_pdu_sync_mode(self.name):
            self.lib.hako_asset_notify_write_pdu_done(self.name)
        self.lib.hako_master_execute()

    def write(self,channel,body):
        size=self.channels[channel]
        raw=bytearray(size)
        struct.pack_into('<6I',raw,0,0x12345678,1,24,size,size,0)
        raw[24:24+len(body)]=body
        buf=c.create_string_buffer(bytes(raw))
        if not self.lib.hako_asset_write_pdu(self.name,self.robot,channel,buf,size):
            raise RuntimeError(f'Avatar PDU write failed: channel {channel}')

    def publish(self,plant,armed,t):
        from research_plant import sim
        x=plant.x; r=sim.rotation(x[6:10])
        angles=np.array([np.arctan2(r[2,1],r[2,2]),np.arcsin(np.clip(-r[2,0],-1,1)),np.arctan2(r[1,0],r[0,0])])
        # Avatar expects ROS x-forward/y-left/z-up, not NED/FRD.
        self.write(1,struct.pack('<6d',*(x[:3]*[1,-1,-1]),*(angles*[1,-1,-1])))
        motor=bytearray(88)
        struct.pack_into('<Q16fB',motor,0,round(t*1e6),*(list(plant.command if armed else np.zeros(4))+[0]*12),128 if armed else 0)
        self.write(0,motor)
        self.write(4,struct.pack('<3d2I',16.8,plant.voltage,24.,0,0))

    def wind(self):
        size=self.channels[3]; buf=c.create_string_buffer(size)
        if self.lib.hako_asset_read_pdu(self.name,self.robot,3,buf,size):
            if struct.unpack_from('<I',buf.raw)[0]==0x12345678:
                wind=np.array(struct.unpack_from('<3d',buf.raw,32))*[1,-1,-1]
                if np.isfinite(wind).all(): return wind
        return np.zeros(3)
