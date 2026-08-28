import json
from pathlib import Path
from types import SimpleNamespace

import nju_agent.__main__ as main_module
from nju_agent.agent import run_agent, run_chat_session
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
                            type="message",
                            content=[
                                SimpleNamespace(type="output_text", text="start"),
                            ],
                        ),
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
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
    )

    assert result == "done"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert calls[0]["input"][0]["role"] == "user"
    assert calls[1]["input"][-1]["type"] == "function_call_output"


def test_main_uses_settings_and_chat_session(monkeypatch) -> None:
    captured = {}

    def fake_load_settings():
        return Settings(api_key="key", model="deepseek-test", max_steps=1)

    def fake_run_chat_session(*, workspace_root, settings, client=None, logger=None, input_fn=None):
        captured["workspace_root"] = workspace_root
        captured["settings"] = settings
        return None

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "run_chat_session", fake_run_chat_session)

    assert main_module.main([]) == 0
    assert captured["workspace_root"] == Path.cwd()


def test_run_chat_session_keeps_conversation_history(tmp_path: Path) -> None:
    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                id=f"resp-{len(calls)}",
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[
                            SimpleNamespace(type="output_text", text=f"done-{len(calls)}"),
                        ],
                    )
                ],
                output_text=f"done-{len(calls)}",
            )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    inputs = iter(["first task", "second task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert calls[0]["input"][0]["content"] == "first task"
    assert any(item.get("content") == "second task" for item in calls[1]["input"])
    assert any(item.get("content") == "done-1" for item in calls[1]["input"])
    assert any(line == "进入对话模式，输入 /exit 退出" for line in logs)
