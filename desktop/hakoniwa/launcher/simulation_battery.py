"""Publish the research plant's constant-voltage supply, simulation only."""
import math
from pymavlink import mavutil


class SimulationBattery:
    def __init__(self,port,system,voltage):
        if not math.isfinite(voltage) or not 14.07<=voltage<=16.36:
            raise ValueError('Voltage outside simulated motor calibration')
        self.voltage=voltage
        self.link=mavutil.mavlink_connection(f'udpout:127.0.0.1:{port}',
            source_system=system,source_component=180)

    def publish(self):
        # Four cells, same total voltage as the motor model. Unmodelled current
        # and temperature are unavailable. SOC is only a voltage-based display;
        # this plant has no discharge dynamics, so it does not drain with time.
        cells=[round(self.voltage*1000/4)]*4+[65535]*6
        soc=round(100*min(1.,max(0.,(self.voltage/4-3.5)/(.7))))
        self.link.mav.battery_status_send(0,mavutil.mavlink.MAV_BATTERY_FUNCTION_ALL,
            mavutil.mavlink.MAV_BATTERY_TYPE_LIPO,32767,cells,-1,-1,-1,soc)

    def close(self): self.link.close()
