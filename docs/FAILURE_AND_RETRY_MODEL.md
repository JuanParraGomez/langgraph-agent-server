# Failure and Retry Model

## State ownership
Workflow state lives in `RunStore` under `run_id`.

## Resume model
`UIFactoryRequest.resume_run_id` allows a new run to resume from the last completed step stored in the previous run result state.

## Retry model
Each node in `ui_factory_v1` retries up to 3 times before failing the run.

## Failure surface
When a node fails, the run stores:
- partial `state`
- `failed_step`
- run logs with step/attempt/error

## Expected operator use
- inspect `/runs/{run_id}`
- inspect `/runs/{run_id}/logs`
- decide whether to call the workflow again with `resume_run_id`
