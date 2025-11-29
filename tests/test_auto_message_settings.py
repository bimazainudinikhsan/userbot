import os
import json
import unittest

from modules.auto_spam import get_settings, update_setting, SETTINGS_FILE

class TestAutoMessageSettings(unittest.TestCase):
    def setUp(self):
        # Backup existing settings file if present
        self.backup = None
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                self.backup = f.read()
        # Start fresh
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            f.write('{}')

    def tearDown(self):
        # Restore backup
        if self.backup is not None:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                f.write(self.backup)
        else:
            try:
                os.remove(SETTINGS_FILE)
            except:
                pass

    def test_default_is_off_and_empty_messages(self):
        s = get_settings(123)
        self.assertFalse(s.get('enabled'))
        self.assertEqual(s.get('messages'), [])

    def test_add_edit_delete_messages(self):
        uid = 456
        s = get_settings(uid)
        msgs = s.get('messages')
        msgs.append('Hello')
        update_setting(uid, 'messages', msgs)
        s2 = get_settings(uid)
        self.assertIn('Hello', s2.get('messages'))

        # Edit first message
        msgs2 = s2.get('messages')
        msgs2[0] = 'Hi there'
        update_setting(uid, 'messages', msgs2)
        s3 = get_settings(uid)
        self.assertEqual(s3.get('messages')[0], 'Hi there')

        # Delete
        msgs3 = s3.get('messages')
        msgs3.pop(0)
        update_setting(uid, 'messages', msgs3)
        s4 = get_settings(uid)
        self.assertEqual(s4.get('messages'), [])

    def test_toggle_enabled(self):
        uid = 789
        s = get_settings(uid)
        self.assertFalse(s.get('enabled'))
        update_setting(uid, 'enabled', True)
        s2 = get_settings(uid)
        self.assertTrue(s2.get('enabled'))

if __name__ == '__main__':
    unittest.main()
