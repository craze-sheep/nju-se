# 1.0 Requirements

This version is the smallest demonstrable coding agent.

Goals:
- Accept one user task from the command line.
- Use an LLM to decide whether to call a tool.
- Support local tools for listing files, reading files, writing files, and running commands.
- Keep a short conversation history in memory.
- Stop after a bounded number of steps.

Non-goals:
- No web UI.
- No multi-agent system.
- No long-term memory.
- No external agent framework.
- No automatic git operations.

Repository goals:
- Keep the development process visible in git history.
- Store plan and development notes in the repository.
