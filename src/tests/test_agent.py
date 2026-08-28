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
    assert logs[0] == "进入对话模式，输入 /exit 退出，/reset 清空历史，/choose 选择对话"
    assert logs[1:] == ["最终结果：done-1", "最终结果：done-2"]
    sessions = json.loads((tmp_path / ".nju_agent" / "sessions.json").read_text(encoding="utf-8"))
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 4
    assert (tmp_path / ".nju_agent" / "sessions" / f"{sessions[0]['id']}.json").exists()


def test_run_chat_session_starts_new_session_by_default(tmp_path: Path) -> None:
    sessions_path = tmp_path / ".nju_agent" / "sessions.json"
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    session = {
        "id": "abc123",
        "title": "旧会话",
        "created_at": 1.0,
        "updated_at": 1.0,
        "message_count": 1,
    }
    sessions_path.write_text(json.dumps([session], ensure_ascii=False), encoding="utf-8")
    session_path = tmp_path / ".nju_agent" / "sessions" / "abc123.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps([{"role": "user", "content": "old"}], ensure_ascii=False),
        encoding="utf-8",
    )

    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="resp-1", output=[], output_text="done")

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    inputs = iter(["new task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert all(item.get("content") != "old" for item in calls[0]["input"])
    assert any(item.get("content") == "new task" for item in calls[0]["input"])
    assert logs[0] == "进入对话模式，输入 /exit 退出，/reset 清空历史，/choose 选择对话"
    assert logs[1] == "最终结果：done"


def test_run_chat_session_choose_loads_saved_history(tmp_path: Path) -> None:
    sessions_path = tmp_path / ".nju_agent" / "sessions.json"
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    session = {
        "id": "abc123",
        "title": "旧会话",
        "created_at": 1.0,
        "updated_at": 1.0,
        "message_count": 1,
    }
    sessions_path.write_text(json.dumps([session], ensure_ascii=False), encoding="utf-8")
    session_path = tmp_path / ".nju_agent" / "sessions" / "abc123.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps([{"role": "user", "content": "old"}], ensure_ascii=False),
        encoding="utf-8",
    )

    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="resp-1", output=[], output_text="done")

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    inputs = iter(["/choose", "1", "new task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert calls[0]["input"][0]["content"] == "old"
    assert any(item.get("content") == "new task" for item in calls[0]["input"])
    assert any(line == "可用会话：" for line in logs)
    assert any(line == "1. 旧会话" for line in logs)
    assert any(line == "历史消息：" for line in logs)
    assert any(line == "你：old" for line in logs)
    assert logs[0] == "进入对话模式，输入 /exit 退出，/reset 清空历史，/choose 选择对话"
    assert logs[-1] == "最终结果：done"


def test_run_chat_session_choose_back_returns_to_current_session(tmp_path: Path) -> None:
    sessions_path = tmp_path / ".nju_agent" / "sessions.json"
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    session = {
        "id": "abc123",
        "title": "旧会话",
        "created_at": 1.0,
        "updated_at": 1.0,
        "message_count": 1,
    }
    sessions_path.write_text(json.dumps([session], ensure_ascii=False), encoding="utf-8")
    session_path = tmp_path / ".nju_agent" / "sessions" / "abc123.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps([{"role": "user", "content": "old"}], ensure_ascii=False),
        encoding="utf-8",
    )

    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="resp-1", output=[], output_text="done")

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    inputs = iter(["/choose", "b", "new task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert all(item.get("content") != "old" for item in calls[0]["input"])
    assert any(item.get("content") == "new task" for item in calls[0]["input"])
    assert any(line == "b. 返回" for line in logs)


def test_run_chat_session_reset_clears_history(tmp_path: Path) -> None:
    sessions_path = tmp_path / ".nju_agent" / "sessions.json"
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    session = {
        "id": "abc123",
        "title": "旧会话",
        "created_at": 1.0,
        "updated_at": 1.0,
        "message_count": 1,
    }
    sessions_path.write_text(json.dumps([session], ensure_ascii=False), encoding="utf-8")
    session_path = tmp_path / ".nju_agent" / "sessions" / "abc123.json"
    session_path.parent.mkdir(parents=True, exist_ok=True)
    session_path.write_text(
        json.dumps([{"role": "user", "content": "old"}], ensure_ascii=False),
        encoding="utf-8",
    )

    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(id="resp-1", output=[], output_text="done")

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    inputs = iter(["/choose", "1", "/reset", "/exit"])

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=lambda _: None,
        input_fn=lambda _: next(inputs),
    )

    assert not session_path.exists()
    sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
    assert sessions[0]["message_count"] == 0


def test_new_session_title_uses_first_user_message(tmp_path: Path) -> None:
    calls = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="resp-1", output=[], output_text="done")

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    sessions_path = tmp_path / ".nju_agent" / "sessions.json"
    sessions_path.parent.mkdir(parents=True, exist_ok=True)
    base_session = {
        "id": "base",
        "title": "旧会话",
        "created_at": 1.0,
        "updated_at": 1.0,
        "message_count": 1,
    }
    sessions_path.write_text(json.dumps([base_session], ensure_ascii=False), encoding="utf-8")
    base_path = tmp_path / ".nju_agent" / "sessions" / "base.json"
    base_path.parent.mkdir(parents=True, exist_ok=True)
    base_path.write_text(
        json.dumps([{"role": "user", "content": "old"}], ensure_ascii=False),
        encoding="utf-8",
    )

    inputs = iter(["帮我看看这个项目里有哪些文件", "/exit"])

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=lambda _: None,
        input_fn=lambda _: next(inputs),
    )

    sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
    assert any(
        session["title"] == "帮我看看这个项目里有哪些文件"
        for session in sessions
    )
