import os
import json
import unittest
from datetime import datetime

from bot_handlers.admin.system import read_manager_control, write_manager_control, backup_and_remove_session

class TestManagerControl(unittest.TestCase):
    def setUp(self):
        try:
            os.remove("manager_control.json")
        except:
            pass
        try:
            os.remove("bot_session.session")
        except:
            pass

    def test_toggle_lock_flag(self):
        data = {"disable_lock": True, "changed_by": 123, "changed_at": datetime.now().isoformat()}
        ok = write_manager_control(data)
        self.assertTrue(ok)
        cfg = read_manager_control()
        self.assertTrue(cfg.get("disable_lock"))

    def test_backup_and_remove_session(self):
        with open("bot_session.session", "w", encoding="utf-8") as f:
            f.write("dummy")
        backup = f"bot_session.session.bak-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        bp = backup_and_remove_session("bot_session.session", backup)
        self.assertFalse(os.path.exists("bot_session.session"))
        if bp:
            self.assertTrue(os.path.exists(bp))

if __name__ == "__main__":
    unittest.main()
