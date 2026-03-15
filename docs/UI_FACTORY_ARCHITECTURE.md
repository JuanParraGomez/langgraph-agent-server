# UI Factory Architecture

## Orchestrator
`langgraph-agent-server` is the single orchestration layer for UI creation/update/publication.

## Graph
`ui_factory_v1`
- `discover_existing_ui`
- `plan_ui_solution`
- `decide_data_strategy`
- `decide_tool_strategy`
- `build_or_update_ui`
- `validate_ui`
- `publish_to_git`
- `resolve_public_state_with_hapi`
- `deploy_via_coolify`
- `register_public_result_in_hapi`
- `ingest_ui_memory_to_rag`
- `synthesize_result`

## External services
- `terminal-tools`: execution fabric
- `hapi`: public-plane / VPS registry and Coolify handoff
- `rag-server`: discovery and memory
- `celery-server`: optional auxiliary jobs, not central in this graph
