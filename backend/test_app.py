import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from app import create_app


class FactoryImportTest(unittest.TestCase):
    def test_import_does_not_access_default_database(self):
        script = """
import sqlite3
from unittest.mock import patch

with patch.object(sqlite3, "connect", side_effect=AssertionError("Import accessed SQLite")) as connect:
    from app import create_app
    assert callable(create_app)
    connect.assert_not_called()
"""
        with TemporaryDirectory() as directory:
            default_database = Path(directory) / "default.sqlite3"
            for configured_path in (None, str(default_database)):
                with self.subTest(DB_PATH=configured_path):
                    environment = os.environ.copy()
                    environment.pop("DB_PATH", None)
                    if configured_path is not None:
                        environment["DB_PATH"] = configured_path
                    result = subprocess.run(
                        [sys.executable, "-c", script],
                        cwd=Path(__file__).parent,
                        env=environment,
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(default_database.exists())


class TaskAPITest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = {"TESTING": True, "DB_PATH": str(Path(self.directory.name) / "tasks.sqlite3")}
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def assert_stats(self, total, completed, pending, deleted=0, completed_deleted=0):
        response = self.client.get("/tasks/stats")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {
            "total": total, "completed": completed, "pending": pending,
            "deleted": deleted, "completed_deleted": completed_deleted,
            "completed_all_time": completed + completed_deleted,
        })

    def test_lifecycle_archive_and_all_time_completion(self):
        self.assertEqual(self.client.get("/tasks").json, [])
        self.assert_stats(0, 0, 0)
        response = self.client.post("/tasks", json={"title": "  Write report  "})
        self.assertEqual(response.status_code, 201)
        task = response.json
        self.assertEqual(task, {"id": 1, "title": "Write report", "completed": False})
        self.assert_stats(1, 0, 1)
        other = self.client.post("/tasks", json={"title": "Send report"}).json
        self.assertNotEqual(task["id"], other["id"])
        self.assert_stats(2, 0, 2)
        for _ in range(2):
            response = self.client.put(f"/tasks/{task['id']}/complete")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json["completed"])
            self.assert_stats(2, 1, 1)
        self.assertEqual(self.client.get("/tasks").json, [response.json, other])
        self.assertEqual(self.client.delete(f"/tasks/{task['id']}").status_code, 204)
        self.assert_stats(1, 0, 1, deleted=1, completed_deleted=1)
        archived = self.client.get("/tasks/deleted").json
        self.assertEqual(archived[0]["title"], "Write report")
        self.assertTrue(archived[0]["completed"])
        self.assertTrue(archived[0]["deleted_at"].endswith("+00:00"))
        self.assertEqual(self.client.delete(f"/tasks/{task['id']}").status_code, 404)
        self.assertEqual(self.client.put(f"/tasks/{task['id']}/complete").status_code, 404)
        self.assertEqual(self.client.delete(f"/tasks/{other['id']}").status_code, 204)
        self.assert_stats(0, 0, 0, deleted=2, completed_deleted=1)
        self.assertEqual(self.client.get("/tasks").json, [])
        self.assertEqual(len(self.client.get("/tasks/deleted").json), 2)

    def test_snapshot_and_data_survive_reopening_database(self):
        first = self.client.post("/tasks", json={"title": "Keep for reference"}).json
        self.client.put(f"/tasks/{first['id']}/complete")
        self.client.delete(f"/tasks/{first['id']}")
        second = self.client.post("/tasks", json={"title": "Still pending"}).json
        before = self.client.get("/tasks/snapshot")
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json["tasks"], [second])
        self.assertEqual(before.json["deletedTasks"][0]["id"], first["id"])
        self.assertEqual(before.json["stats"], self.client.get("/tasks/stats").json)
        reopened = create_app(self.config).test_client()
        self.assertEqual(reopened.get("/tasks/snapshot").json, before.json)
        third = reopened.post("/tasks", json={"title": "Next task"}).json
        self.assertGreater(third["id"], second["id"])

    def test_validation_boundaries_and_missing_ids(self):
        invalid_payloads = [None, [], "text", {}, {"title": None}, {"title": 123},
                            {"title": True}, {"title": "  \n "}, {"title": "x" * 201},
                            {"title": "😀" * 201}, {"title": "Valid", "completed": True}]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/tasks", data=self.app.json.dumps(payload),
                                            content_type="application/json")
                self.assertEqual(response.status_code, 400)
                self.assertTrue(response.json["error"]["message"])
        response = self.client.post("/tasks", data='{"title":', content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json["error"]["message"])
        self.assertEqual(self.client.post("/tasks", data="title=Hello").status_code, 415)
        self.assert_stats(0, 0, 0)
        for title in ["x" * 200, "😀" * 200]:
            self.assertEqual(self.client.post("/tasks", json={"title": title}).status_code, 201)
        for method, path in [("put", "/tasks/999/complete"), ("delete", "/tasks/999"),
                             ("put", "/tasks/no-id/complete"), ("get", "/missing")]:
            with self.subTest(method=method, path=path):
                response = getattr(self.client, method)(path)
                self.assertEqual(response.status_code, 404)
                self.assertTrue(response.json["error"]["message"])
        response = self.client.patch("/tasks")
        self.assertEqual(response.status_code, 405)
        self.assertTrue(response.json["error"]["message"])
        self.assert_stats(2, 0, 2)


if __name__ == "__main__":
    unittest.main()
