import os
import json
import unittest

from modules.auto_spam import get_settings, update_setting, SETTINGS_FILE

class TestAutoMessageReplyOnce(unittest.TestCase):
    def setUp(self):
        self.backup = None
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                self.backup = f.read()
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            f.write('{}')

    def tearDown(self):
        if self.backup is not None:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                f.write(self.backup)
        else:
            try:
                os.remove(SETTINGS_FILE)
            except:
                pass

    def test_replied_chats_default_and_update(self):
        uid = 1001
        s = get_settings(uid)
        self.assertIn('replied_chats', s)
        self.assertIsInstance(s.get('replied_chats'), list)
        self.assertEqual(len(s.get('replied_chats')), 0)

        rc = s.get('replied_chats')
        rc.append(555)
        update_setting(uid, 'replied_chats', rc)

        s2 = get_settings(uid)
        self.assertIn(555, s2.get('replied_chats'))
        self.assertEqual(len(s2.get('replied_chats')), 1)

if __name__ == '__main__':
    unittest.main()
