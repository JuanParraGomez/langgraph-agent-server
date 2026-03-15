from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.schemas import RunRecord, RunStatus


class RunStore:
    def __init__(self, db_path: Path, logs_dir: Path) -> None:
        self.db_path = db_path
        self.logs_dir = logs_dir
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    requested_goal TEXT NOT NULL,
                    selected_graph TEXT NOT NULL,
                    selected_agents TEXT NOT NULL,
                    providers_used TEXT NOT NULL,
                    external_tools_used TEXT NOT NULL,
                    summary TEXT,
                    result TEXT,
                    error TEXT,
                    logs_path TEXT
                )
                """
            )

    def create_run(self, record: RunRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, created_at, started_at, finished_at, status,
                    requested_goal, selected_graph, selected_agents,
                    providers_used, external_tools_used, summary,
                    result, error, logs_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.run_id,
                    record.created_at.isoformat(),
                    _iso(record.started_at),
                    _iso(record.finished_at),
                    record.status.value,
                    record.requested_goal,
                    record.selected_graph,
                    json.dumps(record.selected_agents),
                    json.dumps(record.providers_used),
                    json.dumps(record.external_tools_used),
                    record.summary,
                    json.dumps(record.result) if record.result is not None else None,
                    record.error,
                    record.logs_path,
                ),
            )

    def update_run(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return

        updates: dict[str, Any] = {}
        for key, value in fields.items():
            if key in {"selected_agents", "providers_used", "external_tools_used", "result"} and value is not None:
                updates[key] = json.dumps(value)
            elif key == "status" and isinstance(value, RunStatus):
                updates[key] = value.value
            elif isinstance(value, datetime):
                updates[key] = value.isoformat()
            else:
                updates[key] = value

        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [run_id]

        with self._connect() as conn:
            conn.execute(f"UPDATE runs SET {set_clause} WHERE run_id = ?", values)

    def get_run(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            return None
        return _row_to_record(row)

    def append_log(self, run_id: str, event: str, payload: dict[str, Any]) -> Path:
        path = self.logs_dir / f"{run_id}.log"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "payload": payload,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")
        self.update_run(run_id, logs_path=str(path))
        return path

    def read_logs(self, run_id: str) -> list[dict[str, Any]]:
        path = self.logs_dir / f"{run_id}.log"
        if not path.exists():
            return []

        logs: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    logs.append({"event": "parse_error", "raw": line})
        return logs

    def cancel_run(self, run_id: str, reason: str | None = None) -> RunRecord | None:
        run = self.get_run(run_id)
        if run is None:
            return None
        if run.status in {RunStatus.succeeded, RunStatus.failed, RunStatus.cancelled}:
            return run
        self.update_run(
            run_id,
            status=RunStatus.cancelled,
            finished_at=datetime.now(timezone.utc),
            error=reason or "cancelled_by_user",
        )
        self.append_log(run_id, "run_cancelled", {"reason": reason or "cancelled_by_user"})
        return self.get_run(run_id)

    def is_cancelled(self, run_id: str) -> bool:
        run = self.get_run(run_id)
        return run is not None and run.status == RunStatus.cancelled


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        created_at=_parse_dt(row["created_at"]) or datetime.now(timezone.utc),
        started_at=_parse_dt(row["started_at"]),
        finished_at=_parse_dt(row["finished_at"]),
        status=RunStatus(row["status"]),
        requested_goal=row["requested_goal"],
        selected_graph=row["selected_graph"],
        selected_agents=json.loads(row["selected_agents"]),
        providers_used=json.loads(row["providers_used"]),
        external_tools_used=json.loads(row["external_tools_used"]),
        summary=row["summary"],
        result=json.loads(row["result"]) if row["result"] else None,
        error=row["error"],
        logs_path=row["logs_path"],
    )
