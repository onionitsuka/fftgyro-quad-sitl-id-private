import unittest
from unittest.mock import patch
from simulation_battery import SimulationBattery


class BatteryTests(unittest.TestCase):
    def test_voltage_and_source_match_simulated_vehicle(self):
        with patch('simulation_battery.mavutil.mavlink_connection') as connect:
            supply=SimulationBattery(14910,11,16.)
            connect.assert_called_once_with('udpout:127.0.0.1:14910',source_system=11,source_component=180)
            supply.publish()
            args=connect.return_value.mav.battery_status_send.call_args.args
            self.assertEqual(args[4][:4],[4000]*4)
            self.assertEqual(args[4][4:],[65535]*6)
            self.assertEqual(args[5],-1)  # current unavailable
            self.assertEqual(args[8],71)  # displayed SOC, not time-draining
            supply.close();connect.return_value.close.assert_called_once()

    def test_invalid_supply_rejected_before_network(self):
        with patch('simulation_battery.mavutil.mavlink_connection') as connect:
            for voltage in (float('nan'),0,100):
                with self.assertRaises(ValueError): SimulationBattery(14910,11,voltage)
            connect.assert_not_called()


if __name__=='__main__': unittest.main()
