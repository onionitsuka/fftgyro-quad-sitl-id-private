"""Check zero correction and physical button edge semantics, no real device."""
import struct
import unittest
from unittest.mock import patch
import numpy as np
from pilot_zero import PilotZero, PilotZeroButton


class PilotZeroTests(unittest.TestCase):
    def test_offset_persists_and_vertical_is_unchanged(self):
        zero=PilotZero()
        np.testing.assert_allclose(zero.apply([.6,-.2,.3],request=True),[0,0,.3])
        np.testing.assert_allclose(zero.apply([.7,-.25,.4]),[.1,-.05,.4])
        self.assertEqual(zero.reset_counter,1)
        # Replace bias with raw estimate, not an accumulated corrected value.
        np.testing.assert_allclose(zero.apply([.7,-.25,.4],request=True),[0,0,.4])
        np.testing.assert_allclose(zero.bias,[.7,-.25])
        zero.apply([0,0,0],ground=True)
        np.testing.assert_allclose(zero.bias,0)
        self.assertEqual(zero.reset_counter,3)

    def test_ground_button_does_not_create_a_bias(self):
        zero=PilotZero()
        zero.apply([0,0,0],request=True,ground=True)
        self.assertEqual(zero.count,0)
        self.assertEqual(zero.reset_counter,0)

    def test_init_hold_and_unrelated_buttons_do_not_trigger(self):
        button=PilotZeroButton();button.fd=99
        def poll(events):
            packets=[struct.pack('<IhBB',0,value,kind,number) for value,kind,number in events]
            with patch('pilot_zero.os.read',side_effect=packets+[BlockingIOError()]):
                return button.poll()
        self.assertFalse(poll([(1,129,0),(1,1,0)]))
        self.assertFalse(poll([(0,1,0),(1,1,9),(1,1,10)]))
        self.assertTrue(poll([(1,1,0)]))
        self.assertFalse(poll([(1,1,0)]))
        self.assertTrue(poll([(0,1,0),(1,1,0)]))

    def test_disconnect_reconnect_does_not_trigger(self):
        button=PilotZeroButton();button.fd=99;button.released=True
        with patch('pilot_zero.os.read',side_effect=OSError()),patch('pilot_zero.os.close'):
            self.assertFalse(button.poll())
        self.assertFalse(button.released)
        held=struct.pack('<IhBB',0,1,129,0)
        with patch('pilot_zero.os.open',return_value=98),patch('pilot_zero.os.read',side_effect=[held,BlockingIOError()]):
            self.assertFalse(button.poll())


if __name__=='__main__': unittest.main()
