from app.agents.failure_recovery_agent import FailureRecoveryAgent


def test_classifies_runtime_path_policy_failure() -> None:
    agent = FailureRecoveryAgent()
    analysis = agent.analyze(
        step="build_or_update_ui",
        error=RuntimeError("path policy denied writing task logs"),
        state={"run_id": "run_1", "ui_plan": {"slug": "crm-ui"}},
    )

    assert analysis["classification"] == "runtime_path_policy"
    assert analysis["recoverable"] is False
    assert "rebuild terminal-tools" in " ".join(analysis["user_actions"])


def test_classifies_duplicate_project_create_failure() -> None:
    agent = FailureRecoveryAgent()
    analysis = agent.analyze(
        step="build_or_update_ui",
        error=RuntimeError("hapi_request_failed:/projects/create"),
        state={"run_id": "run_2", "ui_plan": {"slug": "crm-ui"}},
    )

    assert analysis["classification"] == "public_plane_project_create"
    assert analysis["recoverable"] is True
    assert "retry_create_or_recover_existing_project" in analysis["auto_actions"]


def test_classifies_copilot_unavailable_failure() -> None:
    agent = FailureRecoveryAgent()
    analysis = agent.analyze(
        step="build_or_update_ui",
        error=RuntimeError("copilot unavailable"),
        state={"run_id": "run_3", "ui_plan": {"slug": "crm-ui"}},
    )

    assert analysis["classification"] == "terminal_ai_runtime_missing"
    assert analysis["recoverable"] is False
    assert "fnm" in " ".join(analysis["user_actions"])


def test_classifies_copilot_auth_missing_failure() -> None:
    agent = FailureRecoveryAgent()
    analysis = agent.analyze(
        step="build_or_update_ui",
        error=RuntimeError("Error: No authentication information found."),
        state={"run_id": "run_4", "ui_plan": {"slug": "crm-ui"}},
    )

    assert analysis["classification"] == "terminal_ai_auth_missing"
    assert analysis["recoverable"] is False
    assert "Copilot auth directory" in " ".join(analysis["user_actions"])
