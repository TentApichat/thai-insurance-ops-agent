"""SQLite storage: every request, its routing decision, a review queue and an audit log."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS requests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at   TEXT NOT NULL,
    text          TEXT NOT NULL,
    extractor     TEXT NOT NULL,
    request_type  TEXT NOT NULL,
    confidence    REAL NOT NULL,
    fields        TEXT NOT NULL,
    issues        TEXT NOT NULL,
    route         TEXT NOT NULL,
    team          TEXT NOT NULL,
    status        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id  INTEGER NOT NULL REFERENCES requests(id),
    at          TEXT NOT NULL,
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    detail      TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class RequestStore:
    def __init__(self, path: Optional[str] = None):
        self.path = path or os.getenv("TRIAGE_DB", "triage.db")
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def _log(self, request_id: int, actor: str, action: str, detail: dict[str, Any]) -> None:
        self.conn.execute(
            "INSERT INTO audit_log (request_id, at, actor, action, detail) VALUES (?, ?, ?, ?, ?)",
            (request_id, _now(), actor, action, json.dumps(detail, ensure_ascii=False)),
        )

    def save(self, text: str, extraction: dict, issues: list[str], route: str, team: str, extractor: str) -> int:
        status = "queued_for_team" if route == "auto" else "awaiting_review"
        fields = {k: v for k, v in extraction.items() if k not in ("request_type", "confidence")}
        cursor = self.conn.execute(
            """INSERT INTO requests
               (received_at, text, extractor, request_type, confidence, fields, issues, route, team, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _now(), text, extractor, extraction["request_type"], extraction["confidence"],
                json.dumps(fields, ensure_ascii=False), json.dumps(issues, ensure_ascii=False),
                route, team, status,
            ),
        )
        request_id = cursor.lastrowid
        self._log(request_id, f"agent ({extractor})", "triaged", {"route": route, "team": team, "issues": issues})
        self.conn.commit()
        return request_id

    def get(self, request_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
        return self._to_dict(row) if row else None

    def review_queue(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM requests WHERE status = 'awaiting_review' ORDER BY id"
        ).fetchall()
        return [self._to_dict(row) for row in rows]

    def decide(self, request_id: int, reviewer: str, approve: bool, note: str = "") -> dict:
        """Record a person's decision on a request waiting for review."""
        request = self.get(request_id)
        if request is None:
            raise KeyError(f"No request with id {request_id}")
        if request["status"] != "awaiting_review":
            raise ValueError(f"Request {request_id} is not awaiting review (status: {request['status']})")
        status = "queued_for_team" if approve else "rejected"
        self.conn.execute("UPDATE requests SET status = ? WHERE id = ?", (status, request_id))
        self._log(request_id, reviewer, "approved" if approve else "rejected", {"note": note})
        self.conn.commit()
        return self.get(request_id)

    def history(self, request_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT at, actor, action, detail FROM audit_log WHERE request_id = ? ORDER BY id",
            (request_id,),
        ).fetchall()
        return [{**dict(row), "detail": json.loads(row["detail"])} for row in rows]

    @staticmethod
    def _to_dict(row: sqlite3.Row) -> dict:
        data = dict(row)
        data["fields"] = json.loads(data["fields"])
        data["issues"] = json.loads(data["issues"])
        return data
