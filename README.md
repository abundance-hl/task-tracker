# Task Tracker

A lightweight task management app for the take-home assessment: a Python Flask API, a JavaScript React interface, and Docker Compose. Create and complete tasks, move deleted tasks into a reference archive, and view statistics calculated by the backend. SQLite preserves current and archived tasks across restarts.

## Build and run

Install Docker with Docker Compose, start the Docker engine, and ensure local ports **3000** and **5000** are available. The first build needs internet access. No host Python or Node installation, credentials, or manual database setup is required.

```sh
git clone https://github.com/abundance-hl/task-tracker.git
cd task-tracker
docker-compose up --build
```

If your installation provides Compose as a Docker subcommand, use `docker compose up --build`.

- **App:** http://127.0.0.1:3000
- **Backend:** http://127.0.0.1:5000/tasks

Both ports bind to the local machine. Use `127.0.0.1`: on the assessment Mac, `localhost:5000` could resolve to an IPv6 AirPlay listener instead of Flask. The frontend starts after the backend passes its healthcheck.

Useful commands:

```sh
docker-compose up --build -d
docker-compose ps
docker-compose logs --tail=50
docker-compose down
```

`docker-compose down` stops and removes containers while retaining task data. SQLite lives in the named Compose volume `task-data`; using the same Compose project preserves it across container replacement. **`docker-compose down -v` deletes that volume and its tasks.** A fresh clone with a new volume starts empty.

## Use the app

1. Enter a title in **New task** and select **Add task**, or press Enter.
2. Select **Complete** to update a pending task's status and statistics.
3. Select **Delete** to move a task into **Deleted tasks**, retaining its status and deletion time.
4. Select **Refresh** to load changes made through the API or another browser tab.

The interface shows **Current tasks**, **Pending**, and **Completed overall**. Completed overall includes current and archived completions, with a visible breakdown. Deleting unfinished work never increases completion counts.

## Structure

```text
backend/              Flask application, API tests, Python dependencies, Dockerfile
frontend/             React source, UI components, dependency lockfile, Dockerfile
docker-compose.yml    Services, ports, healthchecks, and persistent storage
```

Nginx serves the built React frontend and forwards browser requests from `/api/*` to Flask inside the Compose network. Gunicorn starts Flask through `app:create_app()`. Importing the factory alone does not access SQLite. Database transactions provide a consistent snapshot of current tasks, archived tasks, and statistics.

## API

Task shape: `{ "id": 1, "title": "Write report", "completed": false }`.

| Method | Endpoint | Successful result |
| --- | --- | --- |
| GET | `/tasks` | Current tasks; `200` |
| POST | `/tasks` | Create from `{ "title": "Write report" }`; `201` |
| PUT | `/tasks/<id>/complete` | Completed task; `200` |
| DELETE | `/tasks/<id>` | Archive the task; `204` with no body |
| GET | `/tasks/stats` | Current and historical counts; `200` |
| GET | `/tasks/deleted` | Archived tasks with deletion timestamps; `200` |
| GET | `/tasks/snapshot` | Current tasks, archive, and statistics together; `200` |

Required statistics `total`, `completed`, and `pending` describe current, non-deleted tasks: `total = completed + pending`. Additional fields are `deleted`, `completed_deleted`, and `completed_all_time`. Repeated completion is safe; completing or deleting an archived task returns `404`.

```sh
curl -i -X POST http://127.0.0.1:5000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title":"Write report"}'
curl http://127.0.0.1:5000/tasks
curl http://127.0.0.1:5000/tasks/stats
# Replace 1 with the ID returned by creation.
curl -i -X PUT http://127.0.0.1:5000/tasks/1/complete
curl -i -X DELETE http://127.0.0.1:5000/tasks/1
```

## Assumptions and simplifications

- A local, shared task list: no accounts, authentication, or per-user isolation. Public deployment would require further work.
- Titles are trimmed and must contain 1–200 Unicode code points. Duplicate titles are allowed; generated IDs identify tasks.
- Delete means immediate archival. Restore, permanent deletion, editing, reopening, priorities, due dates, search, and pagination are outside scope.
- SQLite uses one local Docker volume. Backups, distributed deployment, and load testing are outside scope.
- Other browser tabs update on Refresh. The interface waits for confirmed writes and a refreshed snapshot before showing success.
- Known edge case: numeric task IDs beyond SQLite's integer range currently return `500`; explicit range validation remains future work. Normal generated IDs are unaffected.

## How did you handle API errors?

The backend validates requests and returns structured JSON errors, such as:

```json
{ "error": { "code": "invalid_request", "message": "Title must be a non-empty string." } }
```

Invalid titles, malformed JSON, and unexpected creation fields return `400`; non-JSON creation requests return `415`; oversized bodies return `413`. Missing current tasks and unknown routes return `404`, subject to the numeric-range limitation above. Unsupported methods return `405`. SQLite failures are logged and return a readable `503` response.

The frontend displays server messages and provides fallbacks for connection failures, unreadable responses, and a 15-second timeout. Title errors preserve the draft. When an action cannot be confirmed, it marks counts potentially stale and asks for Refresh before another change. Writes are not automatically retried. A successful write followed by a failed refresh gets an explicit message that the change was saved.

## Tests and verification

With the app running:

```sh
docker-compose exec -T backend python -m unittest -v
```

Four test methods cover the task lifecycle, archive/statistics consistency, repeated completion, database reopening, title/JSON validation, missing IDs, and factory import isolation. Each API test uses temporary storage. The import regression runs fresh Python processes and blocks SQLite access during import.

This submission package passed Compose configuration validation, both Docker image builds, and all four tests in an isolated container. The application source is unchanged from the assessment implementation.

The implementation's assessment checks included Docker startup, HTTP lifecycle checks, browser add/complete/delete flows, title boundaries, refresh retention, keyboard focus, narrow-screen layout, and archive retention across container replacement. Those browser checks were agent-operated; this repository does not include an automated browser suite.

Unverified areas include another machine/OS, actual network outages and timeouts, saved-write/failed-refresh recovery, storage failures, request-size boundaries, concurrent load, screen readers, and alternate browsers. There is no CI pipeline yet.

## What tests would you write if given more time?

1. Automated browser tests for the core workflow, keyboard focus, validation, and archive/count consistency.
2. Failure tests for timeouts, failed refreshes, storage errors, and recovery without duplicate creates.
3. API boundary and concurrent-client tests, including oversized task IDs and the 16 KiB request limit.
4. A clean Compose build and container-replacement/data-retention check in CI.

## What would you improve with one extra hour?

1. Fix known bug: Minor API edge case: an extremely large task ID, such as 9223372036854775808, produces 500 Internal Server Error when completing or deleting. It should return a controlled 400 or 404
2. Fix the API GET /tasks/stats 'completed' so that it returns total completed (live completed and archived completed) rather than just live completed. The frontend does but the API does not.
2. Prioritize repeatable regression protection: roughly 40 minutes automating the browser workflow and stale-task recovery, then 20 minutes adding the API tests and frontend build to CI. The keyboard-focus issue was found through interaction testing; automating that flow would make subsequent changes safer. New product features would remain separate work.
