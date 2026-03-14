import json
import threading
import time
import unittest
from http.client import HTTPConnection
from socketserver import TCPServer

from app import AUDIT_LOG, EVENTS, AdminHandler


class AdminApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = TCPServer(("127.0.0.1", 0), AdminHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        EVENTS.clear()
        AUDIT_LOG.clear()

    def request(self, method, path, body=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.port)
        payload = json.dumps(body) if body is not None else None
        conn.request(method, path, body=payload, headers=headers or {})
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        conn.close()
        parsed = json.loads(data) if data and data.startswith(("{", "[")) else data
        return res.status, parsed

    def admin_headers(self, user="alice"):
        return {"X-Role": "admin", "X-User": user, "Content-Type": "application/json"}

    def viewer_headers(self, user="bob"):
        return {"X-Role": "viewer", "X-User": user, "Content-Type": "application/json"}

    def test_role_gate_blocks_admin_endpoints_for_viewer(self):
        status, _ = self.request(
            "POST",
            "/api/admin/events",
            body={
                "name": "Open Blitz",
                "format": "Swiss",
                "time_controls": "3+2",
                "capacity": 12,
                "registration_open_at": "2026-01-01T10:00:00Z",
                "registration_close_at": "2026-01-02T10:00:00Z",
            },
            headers=self.viewer_headers(),
        )
        self.assertEqual(status, 403)

    def test_event_lifecycle_and_audit_log(self):
        status, event = self.request(
            "POST",
            "/api/admin/events",
            body={
                "name": "Spring Cup",
                "format": "Round Robin",
                "time_controls": "10+5",
                "capacity": 4,
                "registration_open_at": "2026-03-01T09:00:00Z",
                "registration_close_at": "2026-03-05T09:00:00Z",
            },
            headers=self.admin_headers(),
        )
        self.assertEqual(status, 200)
        event_id = event["id"]

        status, _ = self.request("POST", f"/api/admin/events/{event_id}/registration/open", headers=self.admin_headers())
        self.assertEqual(status, 200)

        status, _ = self.request(
            "POST",
            f"/api/admin/events/{event_id}/participants/add",
            body={"participant": "player1"},
            headers=self.admin_headers(),
        )
        self.assertEqual(status, 200)

        status, _ = self.request("POST", f"/api/admin/events/{event_id}/start", headers=self.admin_headers())
        self.assertEqual(status, 200)

        status, _ = self.request(
            "POST",
            f"/api/admin/events/{event_id}/rounds/publish",
            body={"round_number": 1},
            headers=self.admin_headers(),
        )
        self.assertEqual(status, 200)

        status, _ = self.request(
            "POST",
            f"/api/admin/events/{event_id}/overrides/report",
            body={"match_id": "M-1", "reason": "Arbiter correction", "result": "1-0"},
            headers=self.admin_headers(),
        )
        self.assertEqual(status, 200)

        status, _ = self.request("POST", f"/api/admin/events/{event_id}/finalize", headers=self.admin_headers())
        self.assertEqual(status, 200)

        status, audit = self.request("GET", "/api/admin/audit-log", headers=self.admin_headers("auditor"))
        self.assertEqual(status, 200)
        actions = [entry["action"] for entry in audit]
        self.assertIn("event.create", actions)
        self.assertIn("event.start", actions)
        self.assertIn("round.publish", actions)
        self.assertIn("event.finalize", actions)


if __name__ == "__main__":
    unittest.main()
