from __future__ import annotations

from datetime import datetime, timezone

from app.models.schemas import RunRecord, RunStatus
from app.storage.run_store import RunStore


def test_run_store_create_update_and_logs(tmp_path):
    store = RunStore(db_path=tmp_path / "runs.db", logs_dir=tmp_path / "logs")
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)

    run = RunRecord(
        run_id="r1",
        created_at=datetime.now(timezone.utc),
        status=RunStatus.pending,
        requested_goal="test goal",
        selected_graph="supervisor_v1",
    )
    store.create_run(run)
    store.update_run("r1", status=RunStatus.running)
    store.append_log("r1", "started", {"x": 1})

    fetched = store.get_run("r1")
    assert fetched is not None
    assert fetched.status == RunStatus.running
    logs = store.read_logs("r1")
    assert logs
    assert logs[0]["event"] == "started"
