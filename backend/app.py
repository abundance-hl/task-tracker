"""Task API backed by a small persistent SQLite store."""

import os
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import BadRequest, HTTPException


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0, 1)),
    deleted_at TEXT DEFAULT NULL
);
"""


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        MAX_CONTENT_LENGTH=16 * 1024,
        DB_PATH=os.environ.get("DB_PATH", str(Path(__file__).with_name("tasks.sqlite3"))),
    )
    if config:
        app.config.update(config)
    with closing(sqlite3.connect(app.config["DB_PATH"], timeout=10)) as database:
        database.execute("PRAGMA journal_mode=WAL")
        database.executescript(SCHEMA)

    def db():
        if "database" not in g:
            g.database = sqlite3.connect(app.config["DB_PATH"], timeout=10)
            g.database.row_factory = sqlite3.Row
        return g.database

    @app.teardown_appcontext
    def close_database(_exception):
        database = g.pop("database", None)
        if database is not None:
            database.close()

    def task_json(row, archived=False):
        task = {"id": row["id"], "title": row["title"], "completed": bool(row["completed"])}
        if archived:
            task["deleted_at"] = row["deleted_at"]
        return task

    def active_tasks():
        return [task_json(row) for row in db().execute(
            "SELECT * FROM tasks WHERE deleted_at IS NULL ORDER BY id")]

    def deleted_tasks():
        return [task_json(row, archived=True) for row in db().execute(
            "SELECT * FROM tasks WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC, id DESC")]

    def statistics():
        row = db().execute("""
            SELECT
                COUNT(CASE WHEN deleted_at IS NULL THEN 1 END) AS total,
                COUNT(CASE WHEN deleted_at IS NULL AND completed = 1 THEN 1 END) AS completed,
                COUNT(CASE WHEN deleted_at IS NULL AND completed = 0 THEN 1 END) AS pending,
                COUNT(CASE WHEN deleted_at IS NOT NULL THEN 1 END) AS deleted,
                COUNT(CASE WHEN deleted_at IS NOT NULL AND completed = 1 THEN 1 END) AS completed_deleted,
                COUNT(CASE WHEN completed = 1 THEN 1 END) AS completed_all_time
            FROM tasks
        """).fetchone()
        return dict(row)

    def error(message, status=400, code="invalid_request"):
        return jsonify(error={"code": code, "message": message}), status

    @app.errorhandler(HTTPException)
    def http_error(exception):
        response = exception.get_response()
        response.data = app.json.dumps({"error": {
            "code": exception.name.lower().replace(" ", "_"),
            "message": exception.description,
        }})
        response.content_type = "application/json"
        return response

    @app.errorhandler(sqlite3.Error)
    def storage_error(exception):
        app.logger.error("Task storage error: %s", exception)
        return error("Task storage is temporarily unavailable. Please refresh and try again.",
                     503, "storage_unavailable")

    @app.after_request
    def no_cache(response):
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/tasks")
    def list_tasks():
        return jsonify(active_tasks())

    @app.get("/tasks/deleted")
    def list_deleted_tasks():
        return jsonify(deleted_tasks())

    @app.get("/tasks/snapshot")
    def task_snapshot():
        with db():
            db().execute("BEGIN")
            snapshot = {"tasks": active_tasks(), "deletedTasks": deleted_tasks(), "stats": statistics()}
        return jsonify(snapshot)

    @app.post("/tasks")
    def create_task():
        if not request.is_json:
            return error("Send a JSON object with Content-Type: application/json.",
                         415, "unsupported_media_type")
        try:
            payload = request.get_json()
        except BadRequest:
            return error("The request body must contain valid JSON.")
        if not isinstance(payload, dict):
            return error("The request body must be a JSON object.")
        if set(payload) - {"title"}:
            return error("Only the title field can be supplied when creating a task.")
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            return error("Title must be a non-empty string.")
        title = title.strip()
        if len(title) > 200:
            return error("Title must be 200 characters or fewer.")
        with db():
            cursor = db().execute("INSERT INTO tasks (title) VALUES (?)", (title,))
            task = {"id": cursor.lastrowid, "title": title, "completed": False}
        return jsonify(task), 201

    @app.put("/tasks/<int:task_id>/complete")
    def complete_task(task_id):
        with db():
            result = db().execute(
                "UPDATE tasks SET completed = 1 WHERE id = ? AND deleted_at IS NULL", (task_id,))
            if result.rowcount == 0:
                return error("Task not found in your current tasks. Refresh the list and try again.",
                             404, "not_found")
            task = task_json(db().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())
        return jsonify(task)

    @app.delete("/tasks/<int:task_id>")
    def delete_task(task_id):
        deleted_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with db():
            result = db().execute(
                "UPDATE tasks SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL", (deleted_at, task_id))
            if result.rowcount == 0:
                return error("Task not found in your current tasks. Refresh the list and try again.",
                             404, "not_found")
        return "", 204

    @app.get("/tasks/stats")
    def task_stats():
        return jsonify(statistics())

    return app
