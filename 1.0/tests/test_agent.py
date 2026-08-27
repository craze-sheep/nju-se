import json
from pathlib import Path
from types import SimpleNamespace

import nju_agent.__main__ as main_module
from nju_agent.agent import run_agent
from nju_agent.config import Settings


def test_run_agent_handles_tool_call_then_completion(tmp_path: Path) -> None:
    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return SimpleNamespace(
                    id="resp-1",
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="write_file",
                            arguments=json.dumps(
                                {"relative_path": "hello.txt", "content": "hi"}
                            ),
                            call_id="call-1",
                        )
                    ],
                    output_text="",
                )
            return SimpleNamespace(id="resp-2", output=[], output_text="done")

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    logs: list[str] = []
    result = run_agent(
        "create file",
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="gpt-test", max_steps=3),
        logger=logs.append,
    )

    assert result == "done"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert any(line.startswith("工具调用：write_file") for line in logs)


def test_main_uses_settings_and_agent(monkeypatch) -> None:
    captured = {}

    def fake_load_settings():
        return Settings(api_key="key", model="gpt-test", max_steps=1)

    def fake_run_agent(task, *, workspace_root, settings, client=None, logger=None):
        captured["task"] = task
        captured["workspace_root"] = workspace_root
        captured["settings"] = settings
        return "ok"

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "run_agent", fake_run_agent)

    assert main_module.main(["hello"]) == 0
    assert captured["task"] == "hello"
