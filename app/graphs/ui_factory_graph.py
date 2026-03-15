from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from app.agents.failure_recovery_agent import FailureRecoveryAgent
from app.adapters.hapi_client import HapiClient, HapiClientError
from app.adapters.rag_server_adapter import RagServerAdapter
from app.adapters.terminal_tools_adapter import TerminalToolsAdapter
from app.core.settings import Settings

LogFn = Callable[[str, dict[str, Any]], None]


class UIFactoryStepError(RuntimeError):
    def __init__(self, step: str, message: str) -> None:
        super().__init__(message)
        self.step = step


class UIFactoryCancelledError(RuntimeError):
    def __init__(self, step: str, message: str = "cancelled_by_user") -> None:
        super().__init__(message)
        self.step = step


class UIFactoryGraph:
    STEPS = [
        "discover_existing_ui",
        "plan_ui_solution",
        "classify_ui_complexity",
        "decide_data_strategy",
        "decide_tool_strategy",
        "ensure_project_workspace",
        "plan_workspace_changes",
        "run_ui_planning",
        "consolidate_ui_plan",
        "create_ui_task_list",
        "run_ui_execution",
        "integrate_ui_work",
        "validate_ui",
        "publish_to_git",
        "resolve_public_state_with_hapi",
        "deploy_via_coolify",
        "ensure_public_availability",
        "register_public_result_in_hapi",
        "ingest_ui_memory_to_rag",
        "synthesize_result",
    ]

    def __init__(
        self,
        *,
        settings: Settings,
        terminal: TerminalToolsAdapter,
        rag: RagServerAdapter,
        hapi: HapiClient,
        recovery: FailureRecoveryAgent | None = None,
        is_cancelled: Callable[[str], bool] | None = None,
    ) -> None:
        self.settings = settings
        self.terminal = terminal
        self.rag = rag
        self.hapi = hapi
        self.recovery = recovery or FailureRecoveryAgent()
        self.is_cancelled = is_cancelled or (lambda _run_id: False)

    async def run(self, *, request: dict[str, Any], run_id: str, previous_state: dict[str, Any] | None, log: LogFn) -> dict[str, Any]:
        state = dict(previous_state or {})
        state.setdefault("request", request)
        state.setdefault("run_id", run_id)
        state.setdefault("goal", request["goal"])
        state.setdefault("context", request.get("context", {}))
        state.setdefault("node_results", {})
        start_index = 0
        if previous_state and previous_state.get("last_completed_step") in self.STEPS:
            start_index = self.STEPS.index(previous_state["last_completed_step"]) + 1
        for step in self.STEPS[start_index:]:
            state = await self._execute_step(step, state, log)
        return state

    async def _execute_step(self, step: str, state: dict[str, Any], log: LogFn) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, 4):
            if self.is_cancelled(state["run_id"]):
                log("ui_factory_step_cancelled", {"step": step, "attempt": attempt})
                raise UIFactoryCancelledError(step)
            log("ui_factory_step_started", {"step": step, "attempt": attempt})
            try:
                node = getattr(self, step)
                result = await node(state)
                state["node_results"][step] = result
                state["last_completed_step"] = step
                log("ui_factory_step_completed", {"step": step, "attempt": attempt})
                return state
            except UIFactoryCancelledError:
                raise
            except Exception as exc:
                last_error = exc
                log("ui_factory_step_failed", {"step": step, "attempt": attempt, "error": str(exc)})
                analysis = self.recovery.analyze(step=step, error=exc, state=state)
                state.setdefault("recovery", {})[step] = analysis
                log("ui_factory_step_recovery", {"step": step, "attempt": attempt, "analysis": analysis})
        raise UIFactoryStepError(step, str(last_error))

    async def discover_existing_ui(self, state: dict[str, Any]) -> dict[str, Any]:
        request = state["request"]
        goal = state["goal"]
        slug = self._slugify(request.get("slug") or request.get("app_name") or goal)
        public_app = await self.hapi.get_public_app_by_slug(slug)
        rag_memory = await self.rag.research(
            question=goal,
            tenant_id=request.get("tenant_id") or self.settings.rag_default_tenant_id,
            filters={"artifact_type": "ui_project_docs"},
            top_k=5,
        )
        action = "update" if public_app else "create"
        project_slug = None
        if public_app:
            project_slug = public_app.get("project_slug") or public_app.get("slug")
        elif request.get("context", {}).get("project_slug"):
            project_slug = request["context"]["project_slug"]
        state["discovery"] = {
            "slug": slug,
            "action": action,
            "public_app": public_app,
            "rag_memory": rag_memory,
            "project_slug": project_slug or slug,
        }
        return state["discovery"]

    async def plan_ui_solution(self, state: dict[str, Any]) -> dict[str, Any]:
        goal = state["goal"].lower()
        request = state["request"]
        slug = state["discovery"]["slug"]
        name = request.get("app_name") or slug.replace("-", " ").title()
        if any(token in goal for token in ["landing", "sitio", "static", "html"]):
            framework = "static-html"
            app_type = "static_html"
            template = "static-html-starter"
        elif any(token in goal for token in ["dashboard", "ventas", "inventario", "filtros", "graficos", "gráficos"]):
            framework = "nextjs"
            app_type = "nextjs"
            template = "nextjs-starter"
        else:
            framework = "react"
            app_type = "react"
            template = "react-starter"
        state["ui_plan"] = {
            "action": state["discovery"]["action"],
            "slug": slug,
            "name": name,
            "framework": framework,
            "app_type": app_type,
            "template": request.get("context", {}).get("template") or template,
            "project_type": request.get("project_type", "long_lived"),
            "rationale": f"Framework selected from prompt heuristics for goal '{state['goal']}'.",
        }
        return state["ui_plan"]

    async def decide_data_strategy(self, state: dict[str, Any]) -> dict[str, Any]:
        goal = state["goal"].lower()
        context = state["context"]
        if context.get("data_strategy"):
            strategy = context["data_strategy"]
        elif any(token in goal for token in ["postgres", "mysql", "sql"]):
            strategy = {"mode": "sql", "source": "database", "notes": "Use SQL-backed read models."}
        elif any(token in goal for token in ["graphql"]):
            strategy = {"mode": "graphql", "source": "api", "notes": "Use typed GraphQL queries."}
        elif any(token in goal for token in ["rest", "api"]):
            strategy = {"mode": "rest", "source": "api", "notes": "Consume REST endpoints with typed clients."}
        elif any(token in goal for token in ["csv", "excel"]):
            strategy = {"mode": "csv", "source": "file", "notes": "Seed with CSV import pipeline."}
        else:
            strategy = {"mode": "mock_data", "source": "local", "notes": "Bootstrap with deterministic mock data."}
        state["data_strategy"] = strategy
        return strategy

    async def classify_ui_complexity(self, state: dict[str, Any]) -> dict[str, Any]:
        goal = state["goal"].lower()
        context = state["context"]
        score = 1
        reasons: list[str] = []
        tokens = {
            "dashboard": 2,
            "filtros": 1,
            "graficos": 1,
            "gráficos": 1,
            "tabla": 1,
            "drill-down": 2,
            "drill down": 2,
            "navegacion": 1,
            "navegación": 1,
            "next.js": 1,
            "nextjs": 1,
            "crud": 2,
        }
        for token, weight in tokens.items():
            if token in goal:
                score += weight
                reasons.append(token)
        if state["ui_plan"]["framework"] == "nextjs":
            score += 1
            reasons.append("framework:nextjs")
        if context.get("priority") == "quality":
            score += 1
            reasons.append("priority:quality")
        if score >= 7:
            level = "complex"
        elif score >= 4:
            level = "medium"
        else:
            level = "simple"
        classification = {"level": level, "score": score, "reasons": reasons}
        state["complexity"] = classification
        return classification

    async def decide_tool_strategy(self, state: dict[str, Any]) -> dict[str, Any]:
        complexity = state["complexity"]["level"]
        context = state.get("context") or {}
        force_workflow = str(context.get("force_workflow") or "").strip().lower()
        if force_workflow in {"copilot_small_change", "copilot_plan_then_codex"}:
            workflow = force_workflow
            reason = f"Workflow forced by context.force_workflow={force_workflow}."
        else:
            workflow = "copilot_plan_then_codex" if complexity in {"medium", "complex"} else "copilot_small_change"
            reason = "Complexity classifier routed this UI to Copilot planning plus Codex execution/integration." if workflow == "copilot_plan_then_codex" else "Complexity classifier routed this UI to direct Copilot execution."
        steps = ["copilot_plan_parallel", "codex_integrator", "task_execution", "git"] if workflow == "copilot_plan_then_codex" else ["copilot", "git"]
        state["tool_strategy"] = {
            "workflow": workflow,
            "steps": steps,
            "reason": reason,
            "codex_fallback": "copilot",
        }
        return state["tool_strategy"]

    async def ensure_project_workspace(self, state: dict[str, Any]) -> dict[str, Any]:
        discovery = state["discovery"]
        plan = state["ui_plan"]
        if discovery["action"] == "create":
            try:
                created = await self.hapi.create_project(
                    {
                        "name": plan["name"],
                        "lifetime": plan["project_type"],
                        "description": state["goal"],
                        "slug": plan["slug"],
                        "template": plan["template"],
                        "deploy_now": False,
                    }
                )
                project = created["project"]
            except HapiClientError as exc:
                if exc.status_code != 409:
                    raise
                project = await self.hapi.get_project(plan["slug"])
        else:
            project = await self.hapi.get_project(discovery["project_slug"])
        cwd = str((self.settings.ui_factory_repo_root / project["project_root"]).resolve())
        state["project"] = project
        state["project_context"] = await self.hapi.render_project_context(project["slug"])
        workspace = {
            "project": project,
            "cwd": cwd,
            "project_context": state["project_context"],
        }
        state["workspace"] = workspace
        return workspace

    async def plan_workspace_changes(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = state["ui_plan"]
        framework = plan["framework"]
        project_root = state["project"]["project_root"]
        files: list[dict[str, Any]]
        if framework == "nextjs":
            files = [
                {"path": f"{project_root}/README.md", "kind": "doc", "owner": "shared"},
                {"path": f"{project_root}/app.meta.yaml", "kind": "meta", "owner": "shared"},
                {"path": f"{project_root}/deploy.meta.yaml", "kind": "meta", "owner": "shared"},
                {"path": f"{project_root}/app/page.tsx", "kind": "ui", "owner": "copilot"},
                {"path": f"{project_root}/app/layout.tsx", "kind": "ui", "owner": "codex"},
                {"path": f"{project_root}/components/dashboard-shell.tsx", "kind": "ui", "owner": "codex"},
                {"path": f"{project_root}/components/filters-panel.tsx", "kind": "ui", "owner": "copilot"},
                {"path": f"{project_root}/components/region-chart.tsx", "kind": "ui", "owner": "codex"},
                {"path": f"{project_root}/components/region-table.tsx", "kind": "ui", "owner": "copilot"},
                {"path": f"{project_root}/lib/mock-data.ts", "kind": "data", "owner": "copilot"},
            ]
        elif framework == "static-html":
            files = [
                {"path": f"{project_root}/README.md", "kind": "doc", "owner": "shared"},
                {"path": f"{project_root}/app.meta.yaml", "kind": "meta", "owner": "shared"},
                {"path": f"{project_root}/deploy.meta.yaml", "kind": "meta", "owner": "shared"},
                {"path": f"{project_root}/index.html", "kind": "ui", "owner": "copilot"},
            ]
        else:
            files = [
                {"path": f"{project_root}/README.md", "kind": "doc", "owner": "shared"},
                {"path": f"{project_root}/app.meta.yaml", "kind": "meta", "owner": "shared"},
                {"path": f"{project_root}/deploy.meta.yaml", "kind": "meta", "owner": "shared"},
                {"path": f"{project_root}/src/App.tsx", "kind": "ui", "owner": "copilot"},
                {"path": f"{project_root}/src/components/Dashboard.tsx", "kind": "ui", "owner": "codex"},
            ]
        workspace_plan = {
            "project_root": project_root,
            "files": files,
            "notes": [
                "Only touch files assigned in this workspace plan unless integration requires README or metadata alignment.",
                "Shared files must be kept consistent after code changes.",
            ],
        }
        state["workspace_plan"] = workspace_plan
        return workspace_plan

    async def run_ui_planning(self, state: dict[str, Any]) -> dict[str, Any]:
        if state["tool_strategy"]["workflow"] != "copilot_plan_then_codex":
            planning = {"skipped": True, "reason": "workflow_does_not_require_planning"}
            state["planning"] = planning
            return planning

        objectives = self._build_planning_objectives(state)
        coroutines = [
            self.terminal.run_copilot_plan(
                objective=item["objective"],
                cwd=state["workspace"]["cwd"],
                timeout_seconds=min(self.settings.ui_factory_copilot_plan_timeout_seconds, 1200),
            )
            for item in objectives
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        tasks: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for item, result in zip(objectives, results, strict=True):
            if isinstance(result, Exception):
                failures.append({"name": item["name"], "error": str(result)})
                continue
            try:
                self._assert_terminal_task_ok(result, f"run_ui_planning.{item['name']}")
                tasks.append({"name": item["name"], "objective": item["objective"], "task": result})
            except Exception as exc:
                failures.append({"name": item["name"], "error": str(exc), "task": result})
        if len(tasks) < 2:
            raise UIFactoryStepError("run_ui_planning", f"insufficient planning subtasks completed: {failures}")
        planning_summary = "\n\n".join(
            f"[{item['name']}]\n{((item['task'].get('result') or {}).get('stdout') or '').strip()}"
            for item in tasks
            if ((item["task"].get("result") or {}).get("stdout") or "").strip()
        )
        planning = {
            "parallelized": True,
            "tasks": tasks,
            "failures": failures,
            "planning_summary": planning_summary,
        }
        state["planning"] = planning
        return planning

    async def consolidate_ui_plan(self, state: dict[str, Any]) -> dict[str, Any]:
        if state["tool_strategy"]["workflow"] != "copilot_plan_then_codex":
            consolidated = {"skipped": True, "reason": "workflow_does_not_require_consolidation"}
            state["planning_consolidation"] = consolidated
            return consolidated
        objective = self._build_consolidation_objective(state)
        consolidation_task = await self._run_codex_with_fallback(
            state=state,
            objective=objective,
            cwd=state["workspace"]["cwd"],
            timeout_seconds=min(self.settings.ui_factory_execution_timeout_seconds, 1800),
            step_name="consolidate_ui_plan",
        )
        self._assert_terminal_task_ok(consolidation_task, "consolidate_ui_plan")
        consolidated = {
            "consolidation_task": consolidation_task,
            "plan_text": ((consolidation_task.get("result") or {}).get("stdout") or "").strip(),
        }
        state["planning_consolidation"] = consolidated
        return consolidated

    async def create_ui_task_list(self, state: dict[str, Any]) -> dict[str, Any]:
        plan = state["ui_plan"]
        workspace_plan = state["workspace_plan"]
        complexity = state["complexity"]["level"]
        if state["tool_strategy"]["workflow"] == "copilot_small_change":
            tasks = [
                {
                    "task_id": "task_ui_single",
                    "title": "Apply requested UI update",
                    "status": "pending",
                    "tool": "copilot",
                    "difficulty": "simple",
                    "target_paths": [item["path"] for item in workspace_plan["files"] if item["kind"] == "ui"],
                }
            ]
        else:
            tasks = [
                {
                    "task_id": "task_ui_shell",
                    "title": "Build shell, navigation and layout",
                    "status": "pending",
                    "tool": "codex" if complexity == "complex" else "copilot",
                    "difficulty": "complex" if complexity == "complex" else "medium",
                    "target_paths": [item["path"] for item in workspace_plan["files"] if "layout" in item["path"] or "shell" in item["path"] or "page" in item["path"]],
                },
                {
                    "task_id": "task_ui_data",
                    "title": "Build mock data, filters and state",
                    "status": "pending",
                    "tool": "copilot",
                    "difficulty": "medium",
                    "target_paths": [item["path"] for item in workspace_plan["files"] if item["kind"] == "data" or "filter" in item["path"] or "table" in item["path"]],
                },
                {
                    "task_id": "task_ui_charts",
                    "title": "Build charts, drill-down and visual summaries",
                    "status": "pending",
                    "tool": "codex" if complexity == "complex" else "copilot",
                    "difficulty": "complex" if complexity == "complex" else "medium",
                    "target_paths": [item["path"] for item in workspace_plan["files"] if "chart" in item["path"] or "Dashboard" in item["path"]],
                },
            ]
        task_list = {
            "tasks": tasks,
            "updated_at": state["run_id"],
            "workspace_plan": workspace_plan,
            "integration_owner": "codex",
            "response_contract": {
                "final_summary_required": True,
                "public_url_required": True,
            },
        }
        state["task_list"] = task_list
        return task_list

    async def run_ui_execution(self, state: dict[str, Any]) -> dict[str, Any]:
        cwd = state["workspace"]["cwd"]
        task_list = state["task_list"]["tasks"]

        async def _run_subtask(task: dict[str, Any]) -> dict[str, Any]:
            objective = self._build_task_execution_objective(state, task)
            if task["tool"] == "codex":
                result = await self._run_codex_with_fallback(
                    state=state,
                    objective=objective,
                    cwd=cwd,
                    timeout_seconds=self.settings.ui_factory_execution_timeout_seconds,
                    step_name=f"run_ui_execution.{task['task_id']}",
                )
            else:
                result = await self.terminal.run_copilot(
                    objective=objective,
                    cwd=cwd,
                    timeout_seconds=self.settings.ui_factory_small_change_timeout_seconds,
                )
            self._assert_terminal_task_ok(result, f"run_ui_execution.{task['task_id']}")
            return {**task, "status": "completed", "result": result}

        results = await asyncio.gather(*[_run_subtask(task) for task in task_list], return_exceptions=True)
        completed: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for task, result in zip(task_list, results, strict=True):
            if isinstance(result, Exception):
                failures.append({**task, "status": "failed", "error": str(result)})
            else:
                completed.append(result)
        if failures:
            state["task_list"]["tasks"] = completed + failures
            raise UIFactoryStepError("run_ui_execution", f"task execution failures: {failures}")
        state["task_list"]["tasks"] = completed
        execution = {"execution_tasks": completed}
        state["execution"] = execution
        return execution

    async def integrate_ui_work(self, state: dict[str, Any]) -> dict[str, Any]:
        workflow = ((state.get("tool_strategy") or {}).get("workflow") or "").strip()
        if workflow == "copilot_small_change":
            integration = {"skipped": True, "reason": "copilot_small_change_workflow"}
            state["integration"] = integration
            return integration
        objective = self._build_integration_objective(state)
        cwd = state["workspace"]["cwd"]
        if (state.get("complexity") or {}).get("level") == "complex":
            integration_task = await self._run_codex_with_fallback(
                state=state,
                objective=objective,
                cwd=cwd,
                timeout_seconds=self.settings.ui_factory_execution_timeout_seconds,
                step_name="integrate_ui_work",
            )
        else:
            integration_task = await self.terminal.run_copilot(
                objective=objective,
                cwd=cwd,
                timeout_seconds=self.settings.ui_factory_small_change_timeout_seconds,
            )
        self._assert_terminal_task_ok(integration_task, "integrate_ui_work")
        integration = {"integration_task": integration_task}
        state["integration"] = integration
        return integration

    async def validate_ui(self, state: dict[str, Any]) -> dict[str, Any]:
        cwd = state["workspace"]["cwd"]
        command = [
            "python3",
            "-c",
            (
                "from pathlib import Path; import sys; "
                "required=['README.md','app.meta.yaml','deploy.meta.yaml']; "
                "missing=[item for item in required if not Path(item).exists()]; "
                "print('ok' if not missing else 'missing:' + ','.join(missing)); "
                "sys.exit(0 if not missing else 1)"
            ),
        ]
        validation = await self.terminal.run_command(
            objective=f"Validate minimal project structure for {state['ui_plan']['slug']}",
            command=command,
            cwd=cwd,
            allow_mutative=False,
            timeout_seconds=self.settings.ui_factory_validation_timeout_seconds,
        )
        self._assert_terminal_task_ok(validation, "validate_ui")
        state["validation"] = validation
        return validation

    async def publish_to_git(self, state: dict[str, Any]) -> dict[str, Any]:
        project_root = state["project"]["project_root"]
        repo_root = str(self.settings.ui_factory_repo_root.resolve())
        branch = self.settings.ui_factory_default_branch
        git_base = self._git_command_base(repo_root)
        git_env = self._git_runtime_env()
        status_task = await self.terminal.run_command(
            objective="Inspect git status before publishing UI changes",
            command=[*git_base, "status", "--short", "--", project_root],
            cwd=repo_root,
            allow_mutative=False,
            env=git_env,
        )
        self._assert_terminal_task_ok(status_task, "publish_to_git.status_task")
        raw_status = (status_task.get("result") or {}).get("stdout") or ""
        commit_task = None
        sync_task = None
        pushed = False
        if raw_status.strip():
            stage_task = await self.terminal.run_command(
                objective="Stage UI project changes",
                command=[*git_base, "add", project_root],
                cwd=repo_root,
                allow_mutative=True,
                env=git_env,
            )
            self._assert_terminal_task_ok(stage_task, "publish_to_git.stage_task")
            commit_task = await self.terminal.run_command(
                objective="Commit UI project changes",
                command=[
                    *git_base,
                    "-c",
                    f"user.name={self.settings.ui_factory_git_user_name}",
                    "-c",
                    f"user.email={self.settings.ui_factory_git_user_email}",
                    "commit",
                    "-m",
                    f"feat(ui-factory): update {state['ui_plan']['slug']} via {state['run_id'][:8]}",
                ],
                cwd=repo_root,
                allow_mutative=True,
                env=git_env,
            )
            self._assert_terminal_task_ok(commit_task, "publish_to_git.commit_task")
        sync_task = await self.terminal.run_command(
            objective=f"Sync local branch with origin/{branch} using autostash rebase",
            command=[
                *git_base,
                "pull",
                "--rebase",
                "--autostash",
                "origin",
                branch,
            ],
            cwd=repo_root,
            allow_mutative=True,
            timeout_seconds=self.settings.ui_factory_git_timeout_seconds,
            env=git_env,
        )
        self._assert_terminal_task_ok(sync_task, "publish_to_git.sync_task")
        ahead_check_task = await self.terminal.run_command(
            objective=f"Check if local branch is ahead of origin/{branch}",
            command=[*git_base, "rev-list", "--left-right", "--count", f"origin/{branch}...HEAD"],
            cwd=repo_root,
            allow_mutative=False,
            env=git_env,
        )
        self._assert_terminal_task_ok(ahead_check_task, "publish_to_git.ahead_check_task")
        ahead_counts = ((ahead_check_task.get("result") or {}).get("stdout") or "").strip().split()
        local_ahead = 0
        if len(ahead_counts) == 2:
            # format: "<origin_only> <head_only>"
            try:
                local_ahead = int(ahead_counts[1])
            except ValueError:
                local_ahead = 0
        should_push = bool(raw_status.strip() or local_ahead > 0)
        if should_push:
            push_task = await self.terminal.run_command(
                objective="Push UI project changes",
                command=[*git_base, "push", "origin", branch],
                cwd=repo_root,
                allow_mutative=True,
                timeout_seconds=self.settings.ui_factory_git_timeout_seconds,
                env=git_env,
            )
            self._assert_terminal_task_ok(push_task, "publish_to_git.push_task")
            pushed = True
        else:
            push_task = None
        sha_task = await self.terminal.run_command(
            objective="Read current commit sha for UI project",
            command=[*git_base, "rev-parse", "HEAD"],
            cwd=repo_root,
            allow_mutative=False,
            env=git_env,
        )
        self._assert_terminal_task_ok(sha_task, "publish_to_git.sha_task")
        commit_sha = ((sha_task.get("result") or {}).get("stdout") or "").strip() or None
        published = {
            "repo_url": self.settings.ui_factory_repo_url,
            "branch": branch,
            "commit_sha": commit_sha,
            "status_task": status_task,
            "commit_task": commit_task,
            "sync_task": sync_task,
            "ahead_check_task": ahead_check_task,
            "local_ahead": local_ahead,
            "push_task": push_task,
            "pushed": pushed,
        }
        state["git_publish"] = published
        return published

    def _git_command_base(self, repo_root: str) -> list[str]:
        return [
            "git",
            "-c",
            f"safe.directory={repo_root}",
        ]

    def _git_ssh_command(self) -> str:
        return (
            f"ssh -F /dev/null -i {self.settings.ui_factory_git_ssh_key_path} "
            "-o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
        )

    def _git_runtime_env(self) -> dict[str, str]:
        return {
            "GIT_SSH_COMMAND": self._git_ssh_command(),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "HOME": "/tmp",
            "XDG_CONFIG_HOME": "/tmp",
        }

    async def resolve_public_state_with_hapi(self, state: dict[str, Any]) -> dict[str, Any]:
        slug = state["ui_plan"]["slug"]
        domain = state["project"].get("domain")
        public_app = await self.hapi.get_public_app_by_slug(slug)
        if public_app is None and domain:
            public_app = await self.hapi.get_public_app_by_domain(domain)
        resolved = {"existing_public_app": public_app, "domain": domain}
        state["public_resolution"] = resolved
        return resolved

    async def deploy_via_coolify(self, state: dict[str, Any]) -> dict[str, Any]:
        project_slug = state["project"]["slug"]
        deploy_payload = {
            "environment_profile": "production" if state["ui_plan"]["project_type"] == "long_lived" else "sandbox",
            "domain": state["project"].get("domain"),
        }
        attempts: list[dict[str, Any]] = []
        deployment: dict[str, Any] | None = None
        max_attempts = max(1, self.settings.ui_factory_deploy_max_attempts)
        for attempt in range(1, max_attempts + 1):
            deployment = await self.hapi.deploy_project(project_slug, deploy_payload)
            attempts.append({"attempt": attempt, "deployment": self._deployment_snapshot(deployment)})
            if self._deployment_is_healthy(deployment):
                break
            if attempt >= max_attempts:
                break
            recovery = await self._recover_publication_failure(
                state=state,
                deployment=deployment,
                attempt=attempt,
            )
            attempts[-1]["recovery"] = recovery
            recovered_deployment = recovery.get("deployment")
            if isinstance(recovered_deployment, dict):
                deployment = recovered_deployment
                attempts[-1]["post_recovery_deployment"] = self._deployment_snapshot(recovered_deployment)
                if self._deployment_is_healthy(recovered_deployment):
                    break
            await asyncio.sleep(max(1, self.settings.ui_factory_deploy_retry_delay_seconds))
        deployment = self._deployment_snapshot(deployment) if deployment else {"status": "failed", "error": "deploy_not_executed"}
        deployment["attempts"] = attempts
        state["deployment"] = deployment
        return deployment

    async def ensure_public_availability(self, state: dict[str, Any]) -> dict[str, Any]:
        deployment = state.get("deployment") or {}
        public_url = self._build_public_url((state.get("project") or {}).get("domain"))
        if not public_url:
            availability = {"checked": False, "reason": "public_url_missing"}
            state["availability_check"] = availability
            return availability
        if not self._deployment_is_healthy(deployment):
            availability = {
                "checked": False,
                "reason": "deployment_not_healthy",
                "deployment_status": deployment.get("status"),
                "url": public_url,
            }
            state["availability_check"] = availability
            return availability

        probe = await self._probe_public_url(public_url, attempts=4, delay_seconds=4)
        if probe.get("available"):
            state["availability_check"] = probe
            return probe

        project_slug = state["project"]["slug"]
        deploy_payload = {
            "environment_profile": "production" if state["ui_plan"]["project_type"] == "long_lived" else "sandbox",
            "domain": state["project"].get("domain"),
        }
        repairs: list[dict[str, Any]] = []
        for repair_attempt in range(1, 3):
            refreshed = await self.hapi.deploy_project(project_slug, deploy_payload)
            refreshed_snapshot = self._deployment_snapshot(refreshed)
            state["deployment"] = refreshed_snapshot
            repair_entry: dict[str, Any] = {
                "attempt": repair_attempt,
                "redeploy": refreshed_snapshot,
            }
            if not self._deployment_is_healthy(refreshed_snapshot):
                auto_fix = await self._auto_fix_deployment_failure(
                    state=state,
                    deployment=refreshed_snapshot,
                    attempt=repair_attempt,
                )
                repair_entry["auto_fix"] = auto_fix
                refreshed = await self.hapi.deploy_project(project_slug, deploy_payload)
                refreshed_snapshot = self._deployment_snapshot(refreshed)
                state["deployment"] = refreshed_snapshot
                repair_entry["post_fix_redeploy"] = refreshed_snapshot
            probe = await self._probe_public_url(public_url, attempts=4, delay_seconds=4)
            repair_entry["probe"] = probe
            repairs.append(repair_entry)
            if probe.get("available"):
                availability = {
                    **probe,
                    "repaired": True,
                    "repairs": repairs,
                }
                state["availability_check"] = availability
                return availability

        availability = {
            "checked": True,
            "available": False,
            "reason": "public_url_unavailable_after_repair",
            "url": public_url,
            "deployment_status": (state.get("deployment") or {}).get("status"),
            "repairs": repairs,
        }
        state["availability_check"] = availability
        return availability

    async def register_public_result_in_hapi(self, state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        deployment = state["deployment"]
        git_meta = state["git_publish"]
        existing = state["public_resolution"].get("existing_public_app")
        public_app = await self.hapi.register_public_app(
            {
                "app_id": existing.get("app_id") if existing else None,
                "slug": state["ui_plan"]["slug"],
                "name": state["ui_plan"]["name"],
                "app_type": state["ui_plan"]["app_type"],
                "framework": state["ui_plan"]["framework"],
                "repo_url": git_meta.get("repo_url"),
                "branch": git_meta.get("branch"),
                "commit_sha": git_meta.get("commit_sha"),
                "public_url": self._build_public_url(project.get("domain")),
                "domain": project.get("domain"),
                "project_slug": project["slug"],
                "status": "ready_for_deploy" if deployment.get("status") != "deployed" else "deployed",
                "data_strategy": state["data_strategy"],
                "tags": ["ui-factory", state["ui_plan"]["framework"]],
                "metadata_json": {
                    "run_id": state["run_id"],
                    "workflow": state["tool_strategy"]["workflow"],
                    "project_root": project["project_root"],
                },
                "correlation_id": state["run_id"],
            }
        )
        if self._supports_public_deployment_record(deployment):
            deployment_payload = {
                "deployment_status": deployment.get("status", "unknown"),
                "provider": deployment.get("provider", "coolify"),
                "public_url": self._build_public_url(project.get("domain")),
                "domain": project.get("domain"),
                "commit_sha": git_meta.get("commit_sha"),
                "details": deployment.get("details", {}),
                "correlation_id": state["run_id"],
            }
            try:
                deployment_record = await self.hapi.record_deployment(public_app["app_id"], deployment_payload)
            except HapiClientError as exc:
                if exc.status_code != 404:
                    raise
                refetched = await self._recover_public_app(project=project, ui_plan=state["ui_plan"], public_app=public_app)
                if refetched is None:
                    raise HapiClientError(
                        "hapi_public_app_recovery_failed",
                        status_code=404,
                        payload={
                            "app_id": public_app.get("app_id"),
                            "slug": state["ui_plan"]["slug"],
                            "domain": project.get("domain"),
                            "original_error": exc.payload,
                        },
                    ) from exc
                public_app = refetched
                deployment_record = await self.hapi.record_deployment(public_app["app_id"], deployment_payload)
        else:
            deployment_record = {
                "app_id": public_app["app_id"],
                "deployment_status": "unknown",
                "provider": deployment.get("provider", "none"),
                "public_url": self._build_public_url(project.get("domain")),
                "domain": project.get("domain"),
                "commit_sha": git_meta.get("commit_sha"),
                "details": {
                    **deployment.get("details", {}),
                    "skipped": True,
                    "reason": deployment.get("error") or "public_deployment_registration_not_applicable",
                },
            }
        state["public_app"] = public_app
        state["public_deployment"] = deployment_record
        return {"public_app": public_app, "deployment": deployment_record}

    async def ingest_ui_memory_to_rag(self, state: dict[str, Any]) -> dict[str, Any]:
        if not state["request"].get("publish_memory", True):
            state["rag_ingest"] = {"published": False}
            return state["rag_ingest"]
        project = state["project"]
        git_meta = state["git_publish"]
        text = (
            f"Goal: {state['goal']}\n"
            f"Action: {state['ui_plan']['action']}\n"
            f"Slug: {state['ui_plan']['slug']}\n"
            f"Name: {state['ui_plan']['name']}\n"
            f"Framework: {state['ui_plan']['framework']}\n"
            f"Template: {state['ui_plan']['template']}\n"
            f"DataStrategy: {state['data_strategy']}\n"
            f"ToolStrategy: {state['tool_strategy']}\n"
            f"RepoURL: {git_meta.get('repo_url')}\n"
            f"Branch: {git_meta.get('branch')}\n"
            f"CommitSHA: {git_meta.get('commit_sha')}\n"
            f"PublicURL: {self._build_public_url(project.get('domain'))}\n"
            f"ProjectRoot: {project.get('project_root')}\n"
        )
        rag = await self.rag.upload_learning(
            text=text,
            tenant_id=state["request"].get("tenant_id") or self.settings.rag_default_tenant_id,
            title=f"{state['ui_plan']['slug']} ui factory memory",
            metadata={
                "artifact_type": "ui_factory_memory",
                "project_slug": project["slug"],
                "domain": project.get("domain") or "",
                "source_service": "langgraph-agent-server",
                "framework": state["ui_plan"]["framework"],
                "action": state["ui_plan"]["action"],
            },
        )
        if state.get("public_app"):
            await self.hapi.record_sync(
                state["public_app"]["app_id"],
                {
                    "target": "rag",
                    "status": "synced",
                    "details": {"document_id": rag.get("document_id")},
                    "correlation_id": state["run_id"],
                },
            )
        state["rag_ingest"] = rag
        return rag

    async def synthesize_result(self, state: dict[str, Any]) -> dict[str, Any]:
        project = state["project"]
        git_meta = state["git_publish"]
        deployment = state["deployment"]
        public_app = state.get("public_app") or {}
        availability = state.get("availability_check") or {}
        deployment_ok = self._deployment_is_healthy(deployment) or bool(availability.get("available"))
        deployment_status = str(deployment.get("status", "unknown"))
        deferred_statuses = {"deferred", "ready_for_deploy", "ready_for_coolify"}
        requires_followup = False
        if not deployment_ok and deployment_status.lower() in deferred_statuses:
            requires_followup = True
        final_status = "succeeded" if deployment_ok or requires_followup else "failed"
        result = {
            "status": final_status,
            "app_id": public_app.get("app_id"),
            "action_taken": state["ui_plan"]["action"],
            "repo_url": git_meta.get("repo_url"),
            "branch": git_meta.get("branch"),
            "commit_sha": git_meta.get("commit_sha"),
            "public_url": self._build_public_url(project.get("domain")),
            "deployment_status": deployment_status,
            "requires_followup": requires_followup,
            "followup_action": "retry_deploy_when_coolify_is_ready" if requires_followup else None,
            "rag_ingested": bool(state.get("rag_ingest", {}).get("document_id")),
            "summary": f"UI workflow finished for {state['ui_plan']['slug']} with deployment status {deployment_status}.",
            "details": {
                "project_slug": project["slug"],
                "project_root": project["project_root"],
                "framework": state["ui_plan"]["framework"],
                "data_strategy": state["data_strategy"],
                "tool_strategy": state["tool_strategy"],
                "deployment": deployment,
                "availability_check": state.get("availability_check"),
                "public_app": public_app,
                "rag_ingest": state.get("rag_ingest"),
            },
        }
        state["final_result"] = result
        return result

    async def _recover_publication_failure(
        self,
        *,
        state: dict[str, Any],
        deployment: dict[str, Any],
        attempt: int,
    ) -> dict[str, Any]:
        error_text = deployment.get("error") or deployment.get("status") or "deployment_failed"
        analysis = self.recovery.analyze(
            step="deploy_via_coolify",
            error=RuntimeError(str(error_text)),
            state=state,
        )
        recovery: dict[str, Any] = {"analysis": analysis}
        classification = str(analysis.get("classification") or "")
        if classification in {"publishing_plane_temporarily_unavailable", "backend_connectivity"}:
            health = await self.hapi.health()
            try:
                coolify = await self.hapi.coolify_health()
            except HapiClientError as exc:
                coolify = {
                    "reachable": False,
                    "error": str(exc),
                    "status_code": exc.status_code,
                    "payload": exc.payload,
                }
            recovery["health"] = {"hapi": health, "coolify": coolify}
            if not bool(coolify.get("reachable")):
                recovery["decision"] = "defer_until_coolify_available"
                recovery["deployment"] = {
                    **self._deployment_snapshot(deployment),
                    "status": "deferred",
                    "error": None,
                    "details": {
                        **(deployment.get("details") or {}),
                        "reason": "coolify_temporarily_unavailable",
                        "retry_recommended": True,
                        "retry_after_seconds": max(30, self.settings.ui_factory_deploy_retry_delay_seconds * 4),
                    },
                }
                return recovery
        auto_fix = await self._auto_fix_deployment_failure(state=state, deployment=deployment, attempt=attempt)
        recovery["auto_fix"] = auto_fix
        redeploy = await self.hapi.deploy_project(
            state["project"]["slug"],
            {
                "environment_profile": "production" if state["ui_plan"]["project_type"] == "long_lived" else "sandbox",
                "domain": state["project"].get("domain"),
            },
        )
        recovery["deployment"] = self._deployment_snapshot(redeploy)
        return recovery

    async def _auto_fix_deployment_failure(self, *, state: dict[str, Any], deployment: dict[str, Any], attempt: int) -> dict[str, Any]:
        cwd = state["workspace"]["cwd"]
        objective = (
            f"Deployment auto-fix attempt {attempt} for UI project '{state['ui_plan']['slug']}'. "
            f"Latest deploy status: {deployment.get('status')}. Error: {deployment.get('error')}. "
            f"Details: {deployment.get('details')}. "
            "Fix the project so deployment can succeed in Coolify. "
            "Ensure Dockerfile/build files and runtime entry are correct for the selected framework. "
            "Keep README/app.meta.yaml/deploy.meta.yaml consistent only if needed."
        )
        fix_task = await self._run_codex_with_fallback(
            state=state,
            objective=objective,
            cwd=cwd,
            timeout_seconds=min(self.settings.ui_factory_execution_timeout_seconds, 2400),
            step_name="_auto_fix_deployment_failure.fix_task",
        )
        self._assert_terminal_task_ok(fix_task, "_auto_fix_deployment_failure.fix_task")
        fix_validation = await self.validate_ui(state)
        republish = await self.publish_to_git(state)
        return {
            "fix_task": fix_task,
            "validation": fix_validation,
            "republish": republish,
        }

    @staticmethod
    def _deployment_is_healthy(deployment: dict[str, Any]) -> bool:
        status = str(deployment.get("status") or "").lower()
        if deployment.get("deployed") is True:
            return True
        return status in {"deployed", "running", "running:healthy"}

    def _build_planning_objective(self, state: dict[str, Any]) -> str:
        plan = state["ui_plan"]
        return (
            f"Plan the implementation for UI project '{plan['slug']}' using template {plan['template']}. "
            f"Goal: {state['goal']}. Data strategy: {state['data_strategy']}. "
            f"Return a concise implementation plan focused on files, UI structure, data hooks, validation and risks."
        )

    def _build_planning_objectives(self, state: dict[str, Any]) -> list[dict[str, str]]:
        base = self._build_planning_objective(state)
        return [
            {
                "name": "information_architecture",
                "objective": f"{base} Focus this plan on page structure, navigation, screen hierarchy and user flows.",
            },
            {
                "name": "data_and_state",
                "objective": f"{base} Focus this plan on data contracts, mock data, filters, state, tables, charts and drill-down behavior.",
            },
            {
                "name": "delivery_and_validation",
                "objective": f"{base} Focus this plan on files to touch, build strategy, validation, deployment notes and risks.",
            },
        ]

    def _build_consolidation_objective(self, state: dict[str, Any]) -> str:
        planning = state.get("planning") or {}
        summary = planning.get("planning_summary") or ""
        plan = state["ui_plan"]
        return (
            f"Review these planning notes for UI project '{plan['slug']}' and produce one unified execution checklist. "
            f"Do not edit files. Do not run mutative commands. "
            f"Return only a concise final implementation plan with sections: files, components, data/state, validation, risks.\n\n"
            f"Planning notes:\n{summary}"
        )

    def _build_execution_objective(self, state: dict[str, Any]) -> str:
        plan = state["ui_plan"]
        consolidation = (state.get("planning_consolidation") or {}).get("plan_text")
        planning_summary = (state.get("planning") or {}).get("planning_summary")
        extra_plan = consolidation or planning_summary or "No prior planning notes."
        return (
            f"Create or update the UI project '{plan['slug']}' in this directory. "
            f"Framework: {plan['framework']}. Template: {plan['template']}. Goal: {state['goal']}. "
            f"Implementation plan:\n{extra_plan}\n\n"
            f"Implement the UI, keep README/app.meta.yaml/deploy.meta.yaml consistent, and leave the project ready for validation."
        )

    def _build_task_execution_objective(self, state: dict[str, Any], task: dict[str, Any]) -> str:
        workspace_notes = "\n".join(f"- {note}" for note in state["workspace_plan"]["notes"])
        target_paths = ", ".join(task["target_paths"]) if task["target_paths"] else "assigned workspace files"
        return (
            f"Work only on this UI subtask: {task['title']}. "
            f"Goal: {state['goal']}. Framework: {state['ui_plan']['framework']}. "
            f"Target paths: {target_paths}. "
            f"Respect the workspace plan and do not overwrite files owned by other subtasks unless needed for integration safety.\n"
            f"Workspace notes:\n{workspace_notes}\n"
            f"Keep README/app.meta.yaml/deploy.meta.yaml untouched in this step unless the target paths explicitly include them."
        )

    def _build_integration_objective(self, state: dict[str, Any]) -> str:
        task_lines = []
        for task in state["task_list"]["tasks"]:
            stdout = ((task.get("result") or {}).get("result") or {}).get("stdout") or ""
            task_lines.append(f"[{task['task_id']}:{task['tool']}]\n{stdout.strip()}")
        task_summary = "\n\n".join(task_lines)
        return (
            f"Integrate all UI subtasks for project '{state['ui_plan']['slug']}'. "
            f"Review the current files, unify style and imports, ensure README/app.meta.yaml/deploy.meta.yaml remain consistent, "
            f"and fix integration issues before validation.\n\nSubtask outputs:\n{task_summary}"
        )

    @staticmethod
    def _supports_public_deployment_record(deployment: dict[str, Any]) -> bool:
        return deployment.get("status") in {"unknown", "deploying", "ready_for_coolify", "deployed", "failed"}

    async def _run_codex_with_fallback(
        self,
        *,
        state: dict[str, Any],
        objective: str,
        cwd: str,
        timeout_seconds: int,
        step_name: str,
    ) -> dict[str, Any]:
        codex_task = await self.terminal.run_codex(
            objective=objective,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
        )
        if self._terminal_task_succeeded(codex_task):
            return codex_task
        if not self._codex_fallback_enabled(state):
            return codex_task
        copilot_timeout = max(60, min(timeout_seconds, self.settings.ui_factory_small_change_timeout_seconds))
        copilot_task = await self.terminal.run_copilot(
            objective=objective,
            cwd=cwd,
            timeout_seconds=copilot_timeout,
        )
        if self._terminal_task_succeeded(copilot_task):
            metadata = (copilot_task.get("metadata") or {}) if isinstance(copilot_task, dict) else {}
            metadata.update(
                {
                    "fallback_from": "codex",
                    "fallback_step": step_name,
                    "fallback_command": self._codex_fallback_command(state),
                    "codex_error": (codex_task.get("error") if isinstance(codex_task, dict) else None),
                }
            )
            if isinstance(copilot_task, dict):
                copilot_task["metadata"] = metadata
            return copilot_task
        if isinstance(codex_task, dict):
            result = codex_task.get("result") or {}
            result["fallback_error"] = (copilot_task or {}).get("error") if isinstance(copilot_task, dict) else "copilot_fallback_failed"
            codex_task["result"] = result
        return codex_task

    @staticmethod
    def _terminal_task_succeeded(task: dict[str, Any] | None) -> bool:
        if not task:
            return False
        if task.get("status") != "succeeded":
            return False
        result = task.get("result") or {}
        return result.get("ok") is not False

    def _codex_fallback_enabled(self, state: dict[str, Any]) -> bool:
        context = state.get("context") or {}
        raw = context.get("codex_fallback_to_copilot")
        if raw is None:
            return True
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.strip().lower() in {"1", "true", "yes", "on", "copilot"}
        return bool(raw)

    def _codex_fallback_command(self, state: dict[str, Any]) -> str:
        context = state.get("context") or {}
        value = context.get("fallback_command")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return "if codex fails, use copilot and continue"

    async def _probe_public_url(self, public_url: str, *, attempts: int, delay_seconds: int) -> dict[str, Any]:
        timeout = max(5, min(30, self.settings.backend_timeout_seconds))
        probes: list[dict[str, Any]] = []
        for attempt in range(1, max(1, attempts) + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=False) as client:
                    response = await client.get(public_url)
                status_code = response.status_code
                ok = 200 <= status_code < 400
                probes.append({"attempt": attempt, "status_code": status_code, "ok": ok})
                if ok:
                    return {
                        "checked": True,
                        "available": True,
                        "url": public_url,
                        "attempt": attempt,
                        "probes": probes,
                    }
            except Exception as exc:
                probes.append({"attempt": attempt, "ok": False, "error": str(exc)})
            if attempt < attempts:
                await asyncio.sleep(max(1, delay_seconds))
        return {
            "checked": True,
            "available": False,
            "url": public_url,
            "probes": probes,
        }

    @staticmethod
    def _deployment_snapshot(deployment: dict[str, Any] | None) -> dict[str, Any]:
        if not deployment:
            return {}
        return copy.deepcopy(deployment)

    async def _recover_public_app(
        self,
        *,
        project: dict[str, Any],
        ui_plan: dict[str, Any],
        public_app: dict[str, Any],
    ) -> dict[str, Any] | None:
        for candidate_id in [public_app.get("app_id")]:
            if candidate_id:
                found = await self.hapi.get_public_app(candidate_id)
                if found is not None:
                    return found
        for slug in [project.get("slug"), ui_plan.get("slug")]:
            if slug:
                found = await self.hapi.get_public_app_by_slug(slug)
                if found is not None:
                    return found
        domain = project.get("domain")
        if domain:
            found = await self.hapi.get_public_app_by_domain(domain)
            if found is not None:
                return found
        return None

    @staticmethod
    def _build_public_url(domain: str | None) -> str | None:
        if not domain:
            return None
        return f"https://{domain}"

    @staticmethod
    def _assert_terminal_task_ok(task: dict[str, Any] | None, step_name: str) -> None:
        if not task:
            raise UIFactoryStepError(step_name, "terminal-tools returned empty task payload")
        if task.get("status") != "succeeded":
            raise UIFactoryStepError(step_name, task.get("error") or task.get("summary") or "terminal task failed")
        result = task.get("result") or {}
        if result.get("ok") is False:
            raise UIFactoryStepError(step_name, result.get("stderr") or result.get("error") or "terminal task reported failure")

    @staticmethod
    def _slugify(value: str) -> str:
        allowed = []
        for char in value.strip().lower():
            if char.isalnum():
                allowed.append(char)
            elif char in {" ", "_", "-"}:
                allowed.append("-")
        slug = "".join(allowed)
        while "--" in slug:
            slug = slug.replace("--", "-")
        slug = slug.strip("-")
        return slug or "ui-app"
