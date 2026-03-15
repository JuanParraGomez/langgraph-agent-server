from __future__ import annotations

from typing import Any


class FailureRecoveryAgent:
    def analyze(self, *, step: str, error: Exception, state: dict[str, Any]) -> dict[str, Any]:
        message = str(error)
        classification = "unknown_failure"
        recoverable = False
        auto_actions: list[str] = []
        user_actions: list[str] = []

        if "path policy denied writing task logs" in message:
            classification = "runtime_path_policy"
            user_actions = [
                "rebuild terminal-tools with host-mounted runtime paths",
                "ensure terminal-tools uses absolute host paths for data/logs/context",
            ]
        elif "path policy denied cwd usage" in message:
            classification = "workspace_path_denied"
            user_actions = [
                "mount the target workspace into terminal-tools",
                "align path policy with the effective runtime cwd",
            ]
        elif "hapi_request_failed:/projects/create" in message:
            classification = "public_plane_project_create"
            recoverable = True
            auto_actions = ["retry_create_or_recover_existing_project"]
            user_actions = [
                "verify hapi is mounted against the real coolify-server repo",
                "check for prior partial project creation with the same slug",
            ]
        elif "coolify_not_configured" in message or "coolify_disabled" in message:
            classification = "publishing_plane_not_configured"
            user_actions = [
                "set COOLIFY_API_TOKEN in hapi",
                "verify COOLIFY_BASE_URL points to the VPS Coolify instance",
            ]
        elif "coolify_temporarily_unavailable" in message or "no available server" in message or "503" in message:
            classification = "publishing_plane_temporarily_unavailable"
            recoverable = True
            auto_actions = ["check_coolify_health", "retry_deploy_with_backoff", "mark_deferred_if_unavailable"]
            user_actions = [
                "check Coolify server capacity/status in VPS",
                "retry deployment when Coolify is reachable",
            ]
        elif "custom_labels should be base64 encoded" in message or "This field is not allowed." in message:
            classification = "publishing_plane_payload_mismatch"
            recoverable = True
            auto_actions = ["refresh_deploy_payload", "retry_deploy"]
            user_actions = [
                "verify Hapi->Coolify payload schema for current Coolify API version",
                "remove unsupported fields from update payload",
            ]
        elif "copilot unavailable" in message or "binary 'copilot'" in message:
            classification = "terminal_ai_runtime_missing"
            user_actions = [
                "mount the host fnm/node installation into terminal-tools",
                "point COPILOT_BIN to a stable in-container path",
            ]
        elif "No authentication information found" in message:
            classification = "terminal_ai_auth_missing"
            user_actions = [
                "mount the host Copilot auth directory into terminal-tools",
                "or provide COPILOT_GITHUB_TOKEN/GH_TOKEN inside the container",
            ]
        elif "Missing bearer or basic authentication in header" in message or "401 Unauthorized" in message:
            classification = "terminal_ai_provider_auth_missing"
            user_actions = [
                "provide OPENAI_API_KEY to terminal-tools for codex execution",
                "or load the global /home/juan/Documents/.env into the container",
            ]
        elif "Connection error" in message or "unreachable" in message:
            classification = "backend_connectivity"
            recoverable = True
            auto_actions = ["retry_with_backoff"]
            user_actions = [
                "check backend health and host.docker.internal wiring",
            ]
        elif "slug_already_exists" in message or "apps_path_exists" in message or "sandbox_path_exists" in message:
            classification = "duplicate_project_slug"
            recoverable = True
            auto_actions = ["fetch_existing_project_by_slug"]
            user_actions = [
                "reuse the existing project or choose a new slug",
            ]

        notes = [
            f"failed_step={step}",
            f"project_slug={((state.get('ui_plan') or {}).get('slug') or (state.get('discovery') or {}).get('project_slug'))}",
            f"run_id={state.get('run_id')}",
        ]

        return {
            "classification": classification,
            "recoverable": recoverable,
            "auto_actions": auto_actions,
            "user_actions": user_actions,
            "normalized_error": message,
            "notes": notes,
        }
