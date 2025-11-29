import unittest

from firebase_manager import should_block_by_lock

class TestSessionLockPolicy(unittest.TestCase):
    def test_block_when_ip_diff(self):
        lock = {'ip': '1.2.3.4'}
        self.assertTrue(should_block_by_lock(lock, '5.6.7.8'))

    def test_allow_when_ip_same(self):
        lock = {'ip': '10.0.0.1'}
        self.assertFalse(should_block_by_lock(lock, '10.0.0.1'))

    def test_allow_when_no_ip(self):
        lock = {}
        self.assertFalse(should_block_by_lock(lock, '10.0.0.1'))

if __name__ == '__main__':
    unittest.main()
