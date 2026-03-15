# LangGraph <-> hapi Contract

## What LangGraph asks from hapi
- create/bootstrap project roots in `coolify-server`
- read project context
- trigger deploy handoff to Coolify
- register/update public app inventory
- record deployment visibility
- record sync events
- expose Coolify/public-plane health

## What hapi must not do
- no planning
- no node orchestration
- no autonomous retries/workflows
- no tool routing

## Correlation
`run_id` from LangGraph should be sent as `correlation_id` for register/deployment/sync calls when possible.
