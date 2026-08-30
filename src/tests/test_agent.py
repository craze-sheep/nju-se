import json
import builtins
import subprocess
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

import nju_agent.__main__ as main_module
import nju_agent.agent as agent_module
from nju_agent.agent import (
    ACCESS_READ_ONLY,
    ACCESS_WRITE,
    _compact_session_memory_if_needed,
    _visible_conversation,
    run_agent,
    run_chat_session,
    tool_definitions,
)
from nju_agent.config import Settings
from nju_agent.ui import TerminalUI


def _message_response(text: str, *, id_suffix: str = "msg") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"resp-{id_suffix}",
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text=text)],
            )
        ],
        output_text=text,
    )


def _empty_response(text: str = "") -> SimpleNamespace:
    return SimpleNamespace(id="resp-empty", output=[], output_text=text)


def _summary_response() -> SimpleNamespace:
    return _message_response(
        json.dumps(
            {
                "goal": "实现多会话和历史回放",
                "decisions": ["会话默认新建", "会话选择通过 /choose"],
                "important_files": ["src/src/nju_agent/agent.py"],
                "open_tasks": ["加入 history 展示"],
                "user_preferences": [],
                "notes": [],
            },
            ensure_ascii=False,
        ),
        id_suffix="summary",
    )


def _global_memory_response() -> SimpleNamespace:
    return _message_response(
        "# Global Memory\n\n## User Preferences\n- 输出简洁\n",
        id_suffix="global",
    )


def _incremental_memory_response() -> SimpleNamespace:
    return _message_response(
        json.dumps(
            {
                "goal": "继续整理上下文",
                "decisions": ["保留最近 4 轮"],
                "important_files": ["src/src/nju_agent/agent.py"],
                "open_tasks": ["继续压缩旧历史"],
                "user_preferences": ["输出简洁"],
                "notes": [],
            },
            ensure_ascii=False,
        ),
        id_suffix="memory",
    )


def _review_response(
    *,
    summary: str,
    issues: list[str],
    needs_retry: bool,
    retry_advice: str,
) -> SimpleNamespace:
    return _message_response(
        json.dumps(
            {
                "summary": summary,
                "issues": issues,
                "needs_retry": needs_retry,
                "retry_advice": retry_advice,
            },
            ensure_ascii=False,
        ),
        id_suffix="review",
    )


class SequencedResponses:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


def _init_git_repo(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True, capture_output=True, text=True)


def test_compact_session_memory_if_needed_updates_memory(tmp_path: Path) -> None:
    session = {"id": "abc", "memory_compacted_upto": 0, "updated_at": 1.0}
    conversation = []
    for i in range(6):
        conversation.append({"role": "user", "content": f"u{i}"})
        conversation.append({"role": "assistant", "content": f"a{i}"})

    responses = SequencedResponses([_incremental_memory_response()])

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    settings = Settings(
        api_key="key",
        model="deepseek-test",
        context_token_limit=1,
        recent_turns=4,
    )
    memory = _compact_session_memory_if_needed(
        workspace_root=tmp_path,
        active_session=session,
        conversation=conversation,
        session_memory={
            "goal": "",
            "decisions": [],
            "important_files": [],
            "open_tasks": [],
            "user_preferences": [],
            "notes": [],
        },
        client=FakeClient(),
        settings=settings,
    )

    assert memory["goal"] == "继续整理上下文"
    assert session["memory_compacted_upto"] > 0
    assert (tmp_path / ".nju_agent" / "memory" / "abc.json").exists()


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
        access_mode=ACCESS_WRITE,
        logger=logs.append,
    )

    assert result == "done"
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "hi"
    assert calls[0]["input"][0]["role"] == "user"
    assert calls[1]["input"][-1]["type"] == "function_call_output"


def test_visible_conversation_keeps_recent_user_turns() -> None:
    conversation = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
        {"role": "user", "content": "u4"},
        {"role": "assistant", "content": "a4"},
        {"role": "user", "content": "u5"},
        {"role": "assistant", "content": "a5"},
    ]

    visible = _visible_conversation(conversation, 4)

    assert [item["content"] for item in visible if item["role"] == "user"] == ["u2", "u3", "u4", "u5"]


def test_main_uses_settings_and_chat_session(monkeypatch) -> None:
    captured = {}

    def fake_load_settings():
        return Settings(api_key="key", model="deepseek-test", max_steps=1)

    def fake_run_chat_session(*, workspace_root, settings, client=None, logger=None, input_fn=None, background_finalize=False):
        captured["workspace_root"] = workspace_root
        captured["settings"] = settings
        captured["background_finalize"] = background_finalize
        return None

    monkeypatch.setattr(main_module, "load_settings", fake_load_settings)
    monkeypatch.setattr(main_module, "run_chat_session", fake_run_chat_session)

    assert main_module.main([]) == 0
    assert captured["workspace_root"] == Path.cwd()
    assert captured["background_finalize"] is True


def test_run_chat_session_keeps_conversation_history(tmp_path: Path) -> None:
    responses = SequencedResponses(
        [
            _message_response("done-1", id_suffix="1"),
            _message_response("done-2", id_suffix="2"),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    inputs = iter(["first task", "second task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert responses.calls[0]["input"][0]["content"] == "first task"
    assert any(item.get("content") == "second task" for item in responses.calls[1]["input"])
    assert any(item.get("content") == "done-1" for item in responses.calls[1]["input"])
    assert logs == ["最终结果：done-1", "最终结果：done-2"]
    sessions = json.loads((tmp_path / ".nju_agent" / "sessions.json").read_text(encoding="utf-8"))
    assert len(sessions) == 1
    assert sessions[0]["message_count"] == 4
    assert (tmp_path / ".nju_agent" / "sessions" / f"{sessions[0]['id']}.json").exists()
    assert (tmp_path / ".nju_agent" / "memory" / f"{sessions[0]['id']}.json").exists()
    assert (tmp_path / ".nju_agent" / "global_memory.md").exists()
    assert len(responses.calls) == 4


def test_run_chat_session_undo_reverts_last_write_batch(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    responses = SequencedResponses(
        [
            SimpleNamespace(
                id="resp-1",
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="write_file",
                        arguments=json.dumps(
                            {"relative_path": "hello.txt", "content": "new content"}
                        ),
                        call_id="call-1",
                    )
                ],
                output_text="",
            ),
            _empty_response("done"),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    (tmp_path / "hello.txt").write_text("old content", encoding="utf-8")
    subprocess.run(["git", "add", "hello.txt"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    inputs = iter(["/access", "2", "make change", "/undo", "/exit"])

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=lambda _: None,
        input_fn=lambda _: next(inputs),
    )

    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "old content"
    sessions = json.loads((tmp_path / ".nju_agent" / "sessions.json").read_text(encoding="utf-8"))
    session_id = sessions[0]["id"]
    batches_path = tmp_path / ".nju_agent" / "write_batches" / f"{session_id}.json"
    assert batches_path.exists()
    assert json.loads(batches_path.read_text(encoding="utf-8")) == []


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

    responses = SequencedResponses(
        [
            _empty_response("done"),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    inputs = iter(["new task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert all(item.get("content") != "old" for item in responses.calls[0]["input"])
    assert any(item.get("content") == "new task" for item in responses.calls[0]["input"])
    assert logs == ["最终结果：done"]


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

    responses = SequencedResponses(
        [
            _empty_response("done"),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    inputs = iter(["/choose", "1", "new task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert responses.calls[0]["input"][0]["content"] == "old"
    assert any(item.get("content") == "new task" for item in responses.calls[0]["input"])
    assert any(line == "可用会话：" for line in logs)
    assert any(line == "1. 旧会话" for line in logs)
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

    responses = SequencedResponses(
        [
            _empty_response("done"),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    inputs = iter(["/choose", "b", "new task", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert all(item.get("content") != "old" for item in responses.calls[0]["input"])
    assert any(item.get("content") == "new task" for item in responses.calls[0]["input"])
    assert all(line != "b. 返回" for line in logs)


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
            self.responses = SequencedResponses([
                _summary_response(),
                _global_memory_response(),
            ])

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
    responses = SequencedResponses(
        [
            _empty_response("done"),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

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


def test_run_agent_read_only_blocks_write_tool(tmp_path: Path) -> None:
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
                                {"relative_path": "blocked.txt", "content": "nope"}
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

    result = run_agent(
        "test read only",
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        access_mode=ACCESS_READ_ONLY,
        logger=lambda _: None,
    )

    assert result == "done"
    assert {tool["name"] for tool in tool_definitions(ACCESS_READ_ONLY)} == {"list_files", "read_file"}
    assert "write_file" not in {tool["name"] for tool in calls[0]["tools"]}
    assert calls[1]["input"][-1]["type"] == "function_call_output"
    assert not (tmp_path / "blocked.txt").exists()


def test_run_agent_with_subagents_plans_reviews_and_retries(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            index = len(calls)
            if index == 1:
                return _message_response("先检查依赖再写文件", id_suffix="plan")
            if index == 2:
                return SimpleNamespace(
                    id="resp-2",
                    output=[
                        SimpleNamespace(
                            type="function_call",
                            name="write_file",
                            arguments=json.dumps(
                                {"relative_path": "hello.txt", "content": "draft"}
                            ),
                            call_id="call-1",
                        )
                    ],
                    output_text="",
                )
            if index == 3:
                return _message_response("draft done", id_suffix="draft")
            if index == 4:
                return _review_response(
                    summary="需要补一个更完整的结果",
                    issues=["输出太短"],
                    needs_retry=True,
                    retry_advice="请补全说明并保持文件内容更明确。",
                )
            return _message_response("fixed result", id_suffix="final")

    class FakeClient:
        def __init__(self) -> None:
            self.responses = FakeResponses()

    logs: list[str] = []
    result = run_agent(
        "create file",
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        access_mode=ACCESS_WRITE,
        subagents_enabled=True,
        logger=logs.append,
    )

    assert result == "fixed result"
    assert calls[0]["tools"] == []
    assert "规划建议：" in calls[2]["instructions"]
    assert "hello.txt" in calls[3]["input"][0]["content"]
    assert (tmp_path / "hello.txt").read_text(encoding="utf-8") == "draft"
    assert any(line.startswith("规划：") for line in logs)
    assert any(line.startswith("审查：") for line in logs)
    assert any(line.startswith("审查建议重试：") for line in logs)


def test_run_chat_session_can_toggle_subagents(tmp_path: Path) -> None:
    responses = SequencedResponses(
        [
            _message_response("先排个计划", id_suffix="plan"),
            _message_response("done", id_suffix="exec"),
            _review_response(
                summary="结果可接受",
                issues=[],
                needs_retry=False,
                retry_advice="",
            ),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    inputs = iter(["/subagents", "make something", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    sessions = json.loads((tmp_path / ".nju_agent" / "sessions.json").read_text(encoding="utf-8"))
    assert sessions[0]["subagents_enabled"] is True
    assert any(line == "当前分工已切换为：开启" for line in logs)
    assert any(line.startswith("规划：") for line in logs)
    assert any(line.startswith("审查：") for line in logs)
    assert logs[-1] == "最终结果：done"


def test_run_chat_session_rejects_unknown_slash_command_before_model(tmp_path: Path) -> None:
    responses = SequencedResponses(
        [
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    inputs = iter(["/subagent", "/exit"])
    logs: list[str] = []

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=logs.append,
        input_fn=lambda _: next(inputs),
    )

    assert logs == ["错误：没有这个功能：/subagent"]
    assert len(responses.calls) == 0


def test_run_chat_session_default_terminal_ui_emits_final_result(monkeypatch, tmp_path: Path) -> None:
    responses = SequencedResponses(
        [
            _empty_response("done"),
            _summary_response(),
            _global_memory_response(),
        ]
    )

    class FakeClient:
        def __init__(self) -> None:
            self.responses = responses

    class FakeUI:
        def __init__(self) -> None:
            self.outputs: list[str] = []
            self.inputs = iter(["check model", "/exit"])

        def banner(self, **kwargs) -> None:
            self.outputs.append("banner")

        def render_state(self, **kwargs) -> None:
            self.outputs.append(f"state:{kwargs['access_mode']}:{kwargs['subagents_enabled']}")

        def emit(self, message: str) -> None:
            self.outputs.append(message)

        def input(self, prompt: str) -> str:
            self.outputs.append(prompt)
            return next(self.inputs)

        def status(self, message: str, spinner: str = "dots"):
            self.outputs.append(message)
            return nullcontext()

    fake_ui = FakeUI()
    same_input = lambda prompt="": "unused"
    monkeypatch.setattr(builtins, "input", same_input)
    monkeypatch.setattr(agent_module, "create_terminal_ui", lambda: fake_ui)
    monkeypatch.setattr(agent_module.run_chat_session, "__kwdefaults__", {
        **agent_module.run_chat_session.__kwdefaults__,
        "input_fn": same_input,
    })

    run_chat_session(
        workspace_root=tmp_path,
        client=FakeClient(),
        settings=Settings(api_key="key", model="deepseek-test", max_steps=3),
        logger=None,
    )

    assert any(message.startswith("最终结果：") for message in fake_ui.outputs)
    assert any(message == "最终结果：done" for message in fake_ui.outputs)
    assert any(message.startswith("state:") for message in fake_ui.outputs)


def test_terminal_ui_pretty_prints_json_tool_result() -> None:
    console = Console(record=True, width=80)
    ui = TerminalUI(console=console)

    ui.emit('工具结果：[".git", ".nju_agent", "README.txt", "src"]')

    text = console.export_text(clear=False)
    assert ".git" in text
    assert "'src'" in text
    assert text.count("\n") >= 4


def test_terminal_ui_banner_keeps_logo_compact() -> None:
    console = Console(record=True, width=100)
    ui = TerminalUI(console=console)

    ui.banner(
        workspace_root=Path("/home/lzy/project/nju-逮捕在逃offer"),
        model="deepseek-v4-flash",
    )

    text = console.export_text(clear=False)
    assert "Semacode Agent" in text
    assert max(len(line) for line in text.splitlines()) <= 100


def test_terminal_ui_state_is_separate_from_banner() -> None:
    console = Console(record=True, width=100)
    ui = TerminalUI(console=console)

    ui.render_state(access_mode="只读", subagents_enabled=False)

    text = console.export_text(clear=False)
    assert "编辑权限" in text
    assert "subagents" in text


def test_terminal_ui_panels_use_full_width() -> None:
    console = Console(record=True, width=60)
    ui = TerminalUI(console=console)

    ui.emit('工具调用：read_file {"relative_path": "src/src/nju_agent/__init__.py"}')
    ui.emit('工具结果：{"ok": true, "message": "hello"}')
    ui.render_conversation_history(
        [
            {"role": "user", "content": "first line"},
            {"role": "assistant", "content": "second line"},
        ]
    )

    text = console.export_text(clear=False)
    assert "工具调用" in text
    assert "工具结果" in text
    assert "历史会话" in text
    assert max(len(line) for line in text.splitlines()) <= 60
