# 1.0 Implementation Plan

Goal: build a minimal command-line coding agent with local tools and a testable loop.

Architecture:
- `src/nju_agent/tools.py` will hold file and command helpers.
- `src/nju_agent/agent.py` will hold the loop that interprets model output.
- `src/nju_agent/__main__.py` will expose the CLI entry point.
- `tests/` will cover tool behavior and the loop contract.

Tech Stack:
- Python 3.11+
- pytest

Spec:
- `1.0/docs/requirements.md`

Global Constraints:
- No agent framework libraries.
- No hosted code execution services.
- All credentials come from environment variables or untracked config.
- Keep behavior bounded and easy to explain.

---

### Task 1: Project skeleton

**Files:**
- Create: `1.0/src/nju_agent/__init__.py`
- Create: `1.0/src/nju_agent/__main__.py`
- Create: `1.0/src/nju_agent/agent.py`
- Create: `1.0/src/nju_agent/tools.py`
- Create: `1.0/tests/test_tools.py`

**Interfaces:**
- Produces: file and command helpers, plus a CLI entry point.

- [ ] Write the failing test
- [ ] Implement minimal code
- [ ] Verify tests pass

### Task 2: Development notes

**Files:**
- Create: `1.0/docs/log.md`

**Interfaces:**
- Produces: a running record of implementation decisions and verification.

- [ ] Write the initial log entry
- [ ] Keep updating it after each commit
