# Development Log

## 2026-08-27

- Created the 1.0 folder structure for the minimal coding agent.
- Wrote the first requirements and implementation plan.
- Added the first TDD cycle for `list_files`.
- Red check: `PYTHONPATH=1.0/src pytest 1.0/tests/test_tools.py -q` failed because `nju_agent.tools` did not exist.
- Green check: the same command passed with `1 passed`.
- CLI smoke check: `PYTHONPATH=1.0/src python -m nju_agent` printed `Task received: demo`.
- Next step: add file read/write and command execution tools.
