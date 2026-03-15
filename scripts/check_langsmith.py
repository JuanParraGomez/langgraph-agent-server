#!/usr/bin/env python3
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.settings import get_settings
from app.observability.langsmith_setup import configure_langsmith, get_langsmith_client, invoke_graph_traced


async def _probe_task(probe_id: str) -> dict[str, str]:
    return {"probe_id": probe_id, "status": "ok"}


async def main() -> int:
    settings = get_settings()
    config = configure_langsmith(settings)
    if not config.get("enabled"):
        raise RuntimeError("LangSmith is disabled; cannot run probe")

    probe_id = f"langsmith-probe-{uuid4().hex[:12]}"
    await invoke_graph_traced(
        "check_langsmith_probe",
        _probe_task,
        probe_id,
        trace_tags=["langsmith-check", "observability"],
        trace_metadata={"probe_id": probe_id, "service": settings.server_name},
        trace_run_type="tool",
    )

    client = get_langsmith_client()
    since = datetime.now(timezone.utc) - timedelta(minutes=5)
    for _ in range(6):
        runs = list(
            client.list_runs(
                project_name=settings.langsmith_project,
                start_time=since,
                is_root=True,
                limit=30,
            )
        )
        for run in runs:
            run_metadata = (run.extra or {}).get("metadata", {})
            if run.name == "check_langsmith_probe" and run_metadata.get("probe_id") == probe_id:
                print("LANGSMITH_PROBE_OK")
                print(f"project={settings.langsmith_project}")
                print(f"workspace_id={settings.langsmith_workspace_id}")
                print(f"run_id={run.id}")
                print(f"trace_id={run.trace_id}")
                return 0
        await asyncio.sleep(5)

    raise RuntimeError("Probe run not found in LangSmith after retries")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
