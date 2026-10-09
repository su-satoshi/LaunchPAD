# Archive

Status notes from the original AI Job Pilot build (May 2026). Kept for history; they
describe an older version. The current setup and architecture are in the top-level
`README.md`. The old `run_api_tests.sh` was replaced by the pytest suite in `tests/`
(it marked every endpoint as passing on any HTTP 200, and its `head -n -1` didn't run
on macOS).
