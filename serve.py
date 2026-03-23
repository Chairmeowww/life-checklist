#!/usr/bin/env python3
"""
Tiny local server for Life Checklist (STEP Command Central).
Run: python3 serve.py
Open: http://localhost:8080
"""

import json
import os
from datetime import datetime, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8080
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")
# Run from Terminal: python3 ~/Desktop/life-checklist/serve.py
# Data saves to: ~/Desktop/life-checklist/tasks.json

def read_data():
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def write_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def _migrate_data(data):
    """
    Handle data structure migrations:
    - waitingOn: moved from runningLists to top-level array
    - runningLists: now has 'delegate' instead of 'waitingOn'
    - routines.daily: now an object with morning/afternoon/night arrays
      instead of a flat array
    """
    # Migrate waitingOn from runningLists to top-level
    if "waitingOn" not in data:
        running = data.get("runningLists", {})
        if "waitingOn" in running:
            data["waitingOn"] = running.pop("waitingOn")
        else:
            data["waitingOn"] = []

    # Ensure runningLists has 'delegate' key (replaces old waitingOn role)
    running = data.get("runningLists", {})
    if "waitingOn" in running:
        # Move leftover waitingOn items into delegate, then remove
        running.setdefault("delegate", running.pop("waitingOn"))
    if "delegate" not in running:
        running["delegate"] = []

    # Migrate routines.daily from flat array to morning/afternoon/night
    routines = data.get("routines", {})
    daily = routines.get("daily", [])
    if isinstance(daily, list):
        routines["daily"] = {
            "morning": daily,   # existing items default to morning
            "afternoon": [],
            "night": []
        }

    return data


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)

    def end_headers(self):
        # Disable caching so browser always gets latest version
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------
    def do_GET(self):
        if self.path == "/api/tasks":
            data = _migrate_data(read_data())
            self._json_response(data)
        elif self.path == "/api/projects":
            self._json_response(read_data().get("projects", []))
        elif self.path == "/api/running-lists":
            data = _migrate_data(read_data())
            self._json_response(data.get("runningLists", {}))
        elif self.path == "/api/waiting-on":
            data = _migrate_data(read_data())
            self._json_response(data.get("waitingOn", []))
        elif self.path == "/api/routines":
            data = _migrate_data(read_data())
            self._json_response(data.get("routines", {}))
        elif self.path == "/api/calendar":
            self._json_response(read_data().get("calendar", []))
        elif self.path == "/api/desires":
            self._json_response(read_data().get("desires", {}))
        elif self.path == "/api/recommendations":
            self._json_response(read_data().get("recommendations", {}))

        # ----- Google Calendar sync (read) -----
        elif self.path == "/api/google-calendar":
            self._json_response(read_data().get("calendar", []))

        # ----- Celebration / weekly wins -----
        elif self.path == "/api/celebration":
            self._celebration_response()

        elif self.path == "/":
            self.path = "/checklist.html"
            super().do_GET()
        else:
            super().do_GET()

    # ------------------------------------------------------------------
    # POST
    # ------------------------------------------------------------------
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/api/tasks":
            write_data(body)
            self._json_response({"ok": True})

        elif self.path == "/api/brain-dump":
            data = read_data()
            items = body.get("items", [])
            data["inbox"].extend(items)
            write_data(data)
            self._json_response({"ok": True, "inboxCount": len(data["inbox"])})

        # ----- Google Calendar sync (write) -----
        # External agents (OpenClaw/Sam) POST calendar events here
        elif self.path == "/api/google-calendar":
            data = read_data()
            incoming = body if isinstance(body, list) else body.get("events", [])
            calendar = data.get("calendar", [])
            calendar.extend(incoming)
            data["calendar"] = calendar
            write_data(data)
            self._json_response({"ok": True, "synced": len(incoming)})

        # ----- AI suggestion placeholder -----
        # TODO: Wire this to OpenRouter API using the provided apiKey.
        #       The request body contains:
        #         {"type": "next-action", "project": {...},
        #          "apiKey": "...", "provider": "openrouter"}
        #       When implemented, call the OpenRouter completions endpoint
        #       and return the AI-generated next-action suggestion.
        elif self.path == "/api/ai-suggest":
            self._json_response({
                "suggestion": "AI suggestions coming soon - configure OpenRouter API key in settings"
            })

        # ----- Google Calendar event sync (merge, deduplicate) -----
        # Accepts: {"events": [{"date": "...", "description": "...", "source": "google-calendar"}]}
        elif self.path == "/api/sync-gcal":
            data = read_data()
            incoming_events = body.get("events", [])
            calendar = data.get("calendar", [])

            # Build a set of existing (date, description) pairs for dedup
            existing = {
                (e.get("date"), e.get("description"))
                for e in calendar
            }

            added = 0
            for evt in incoming_events:
                key = (evt.get("date"), evt.get("description"))
                if key not in existing:
                    calendar.append(evt)
                    existing.add(key)
                    added += 1

            data["calendar"] = calendar
            write_data(data)
            self._json_response({"ok": True, "synced": added})

        else:
            self.send_error(404)

    # ------------------------------------------------------------------
    # OPTIONS (CORS preflight)
    # ------------------------------------------------------------------
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _json_response(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _celebration_response(self):
        """Return items completed this week and summary stats."""
        data = read_data()
        today = datetime.now().date()
        # Monday of the current week
        week_start = today - timedelta(days=today.weekday())

        completed_this_week = []
        projects_with_completions = set()

        # Check projects for completed tasks (use 'completedDate' if present)
        for proj in data.get("projects", []):
            for task in proj.get("tasks", []):
                if task.get("done"):
                    cd = task.get("completedDate", "")
                    if cd:
                        try:
                            task_date = datetime.strptime(cd, "%Y-%m-%d").date()
                            if task_date >= week_start:
                                completed_this_week.append({
                                    "text": task.get("text", ""),
                                    "project": proj.get("title", ""),
                                    "completedDate": cd
                                })
                                projects_with_completions.add(proj.get("id"))
                        except ValueError:
                            pass
                    # If no completedDate, we still count it as a win
                    # (legacy data) but won't filter by week
                    # — skip for weekly calculation

        # Check running lists
        running = data.get("runningLists", {})
        for list_name, items in running.items():
            if isinstance(items, list):
                for item in items:
                    if item.get("done"):
                        cd = item.get("completedDate", "")
                        if cd:
                            try:
                                item_date = datetime.strptime(cd, "%Y-%m-%d").date()
                                if item_date >= week_start:
                                    completed_this_week.append({
                                        "text": item.get("text", ""),
                                        "list": list_name,
                                        "completedDate": cd
                                    })
                            except ValueError:
                                pass

        # Check top-level completed array
        for item in data.get("completed", []):
            cd = item.get("completedDate", "")
            if cd:
                try:
                    item_date = datetime.strptime(cd, "%Y-%m-%d").date()
                    if item_date >= week_start:
                        completed_this_week.append({
                            "text": item.get("text", ""),
                            "completedDate": cd
                        })
                except ValueError:
                    pass

        self._json_response({
            "completedThisWeek": completed_this_week,
            "projectsAdvanced": len(projects_with_completions),
            "totalCompleted": len(completed_this_week)
        })

    def log_message(self, format, *args):
        # Quieter logs — only show API calls
        try:
            if args and isinstance(args[0], str) and "/api/" in args[0]:
                super().log_message(format, *args)
        except (TypeError, IndexError):
            pass

if __name__ == "__main__":
    print(f"Life Management Dashboard running at http://localhost:{PORT}")
    print(f"Data file: {DATA_FILE}")
    print("Press Ctrl+C to stop\n")
    HTTPServer(("", PORT), Handler).serve_forever()
