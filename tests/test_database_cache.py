import unittest
import types
import time

import database as db

class FakeSheet:
    def __init__(self):
        self.rows = [
            {"User ID": "1", "Nama": "A", "Email": "a@example.com", "Status": "Approved", "Expired": "01-01-2030", "Join Time": "01-01-2020 00:00", "Session String": "", "Permissions": "ALL"},
            {"User ID": "2", "Nama": "B", "Email": "b@example.com", "Status": "Pending", "Expired": "01-01-2030", "Join Time": "01-01-2020 00:00", "Session String": "", "Permissions": "ALL"},
        ]
        self.col_count = 8

    def get_all_records(self):
        return list(self.rows)

    def update_cell(self, row, col, val):
        pass

    def delete_rows(self, row):
        idx = row - 2
        if 0 <= idx < len(self.rows):
            self.rows.pop(idx)

class TestDatabaseCache(unittest.TestCase):
    def setUp(self):
        db.member_sheet = FakeSheet()
        db._CACHE_MEMBERS["data"] = None
        db._CACHE_MEMBERS["ts"] = 0

    def test_cache_read(self):
        data1 = db.get_all_members_safe()
        self.assertEqual(len(data1), 2)
        db.member_sheet.rows.append({"User ID": "3"})
        data2 = db.get_all_members_safe()
        self.assertEqual(len(data2), 2)

    def test_cache_invalidate_on_delete(self):
        self.assertTrue(db.delete_member("2"))
        data = db.get_all_members_safe()
        self.assertEqual(len(data), 1)

    def test_validation_status(self):
        ok = db.update_member_status(2, "Approved")
        self.assertTrue(ok)
        bad = db.update_member_status(2, "X")
        self.assertFalse(bad)

if __name__ == "__main__":
    unittest.main()
