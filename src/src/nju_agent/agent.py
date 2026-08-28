from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import Settings, load_settings
from .llm import build_client, request_response
from .tools import list_files, read_file, run_command, write_file


SYSTEM_PROMPT = """You are a coding agent.
Use the available tools to complete the user's task.
Keep file operations inside the workspace root.
When you finish, answer briefly in Chinese."""


def tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "name": "list_files",
            "description": "列出工作区根目录下的文件和文件夹名称。",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "read_file",
            "description": "读取工作区内的一个文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "相对于工作区根目录的路径。",
                    }
                },
                "required": ["relative_path"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "write_file",
            "description": "在工作区内创建或覆盖一个文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "相对于工作区根目录的路径。",
                    },
                    "content": {
                        "type": "string",
                        "description": "要写入文件的完整文本内容。",
                    },
                },
                "required": ["relative_path", "content"],
                "additionalProperties": False,
            },
            "strict": True,
        },
        {
            "type": "function",
            "name": "run_command",
            "description": "在工作区根目录下执行一个命令并返回输出。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要执行的命令及其参数。",
                    },
                    "timeout": {
                        "type": "number",
                        "description": "超时时间，单位秒。",
                    },
                },
                "required": ["command"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    ]


def _format_tool_result(name: str, result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)


def _conversation_file(workspace_root: Path) -> Path:
    return workspace_root / ".nju_agent" / "conversation.json"


def _sessions_dir(workspace_root: Path) -> Path:
    return workspace_root / ".nju_agent" / "sessions"


def _sessions_index_file(workspace_root: Path) -> Path:
    return workspace_root / ".nju_agent" / "sessions.json"


def _load_conversation(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    conversation: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            conversation.append(item)
    return conversation


def _save_conversation(path: Path, conversation: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(conversation, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _clear_conversation(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _load_sessions_index(path: Path) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []

    sessions: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            sessions.append(item)
    return sessions


def _save_sessions_index(path: Path, sessions: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _session_path(workspace_root: Path, session_id: str) -> Path:
    return _sessions_dir(workspace_root) / f"{session_id}.json"


def _session_label(session: dict[str, Any]) -> str:
    title = str(session.get("title", "")).strip()
    if title:
        return title
    session_id = str(session.get("id", "")).strip()
    if session_id:
        return session_id
    return "未命名会话"


def _print_conversation_history(
    conversation: list[dict[str, Any]],
    logger: Callable[[str], None],
) -> None:
    emit = logger or (lambda _: None)
    if not conversation:
        return

    emit("历史消息：")
    for item in conversation:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        if role == "user":
            emit(f"你：{content}")
        elif role == "assistant":
            emit(f"助手：{content}")


def _derive_session_title(text: str) -> str:
    text = " ".join(text.split()).strip()
    if not text:
        return "新会话"
    return text[:24]


def _create_session_record(title: str = "新会话") -> dict[str, Any]:
    now = time.time()
    timestamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "id": uuid4().hex,
        "title": f"{title} {timestamp}" if title == "新会话" else title,
        "created_at": now,
        "updated_at": now,
        "message_count": 0,
    }


def _choose_session(
    sessions: list[dict[str, Any]],
    input_fn: Callable[[str], str],
    logger: Callable[[str], None],
) -> dict[str, Any] | None:
    emit = logger or (lambda _: None)
    if not sessions:
        return _create_session_record()

    emit("可用会话：")
    for index, session in enumerate(sessions, start=1):
        emit(f"{index}. {_session_label(session)}")
    emit("n. 新建会话")
    emit("b. 返回")

    while True:
        choice = input_fn("选择会话编号，或输入 n 新建，b 返回：").strip().lower()
        if choice in {"b", "back"}:
            return None
        if choice in {"n", "new"}:
            return _create_session_record()
        if choice.isdigit():
            index = int(choice) - 1
            if 0 <= index < len(sessions):
                return sessions[index]
        emit("输入无效，请重新选择")


def _sync_session_state(
    *,
    sessions_index_path: Path,
    sessions: list[dict[str, Any]],
    active_session: dict[str, Any],
    active_session_path: Path,
    conversation: list[dict[str, Any]],
    keep_empty: bool = True,
) -> list[dict[str, Any]]:
    if conversation:
        _save_conversation(active_session_path, conversation)
    elif keep_empty:
        _clear_conversation(active_session_path)
    else:
        sessions = [
            session
            for session in sessions
            if session.get("id") != active_session.get("id")
        ]
        _save_sessions_index(sessions_index_path, sessions)
        return sessions

    active_session["updated_at"] = time.time()
    active_session["message_count"] = len(conversation)
    sessions = _update_session_index(sessions, active_session)
    _save_sessions_index(sessions_index_path, sessions)
    return sessions


def _update_session_index(
    sessions: list[dict[str, Any]],
    active_session: dict[str, Any],
) -> list[dict[str, Any]]:
    next_sessions: list[dict[str, Any]] = []
    found = False
    for session in sessions:
        if session.get("id") == active_session.get("id"):
            next_sessions.append(active_session)
            found = True
        else:
            next_sessions.append(session)
    if not found:
        next_sessions.append(active_session)
    return sorted(
        next_sessions,
        key=lambda item: float(item.get("updated_at", 0.0)),
        reverse=True,
    )


def _should_title_from_first_message(session: dict[str, Any]) -> bool:
    title = str(session.get("title", "")).strip()
    message_count = int(session.get("message_count", 0) or 0)
    return message_count == 0 and title.startswith("新会话")


def _response_item_to_history(item: Any) -> dict[str, Any] | None:
    item_type = getattr(item, "type", None)

    if item_type == "message":
        text = "".join(
            getattr(part, "text", "")
            for part in getattr(item, "content", [])
            if getattr(part, "type", None) == "output_text"
        )
        return {"role": "assistant", "content": text}

    if item_type == "function_call":
        return {
            "type": "function_call",
            "call_id": getattr(item, "call_id", ""),
            "name": getattr(item, "name", ""),
            "arguments": getattr(item, "arguments", "{}"),
        }

    return None


def _call_tool(name: str, arguments: dict[str, Any], workspace_root: Path) -> str:
    root = str(workspace_root)

    try:
        if name == "list_files":
            return json.dumps(list_files(root), ensure_ascii=False)
        if name == "read_file":
            return read_file(root, arguments["relative_path"])
        if name == "write_file":
            write_file(root, arguments["relative_path"], arguments["content"])
            return "success"
        if name == "run_command":
            result = run_command(
                root,
                arguments["command"],
                timeout=float(arguments.get("timeout", 10.0)),
            )
            return _format_tool_result(
                name,
                {
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
        return f"错误：未知工具 {name}"
    except Exception as exc:
        return f"错误：{exc}"


def _run_conversation(
    conversation: list[dict[str, Any]],
    *,
    workspace_root: Path,
    client: Any | None = None,
    settings: Settings | None = None,
    logger: Callable[[str], None] | None = print,
) -> str:
    settings = settings or load_settings()
    client = client or build_client(settings)
    workspace_root = workspace_root.resolve()
    emit = logger or (lambda _: None)

    response = None

    for _ in range(settings.max_steps):
        response = request_response(
            client,
            model=settings.model,
            input=conversation,
            tools=tool_definitions(),
            instructions=SYSTEM_PROMPT,
        )

        tool_calls = [
            item
            for item in getattr(response, "output", [])
            if getattr(item, "type", None) == "function_call"
        ]

        for item in getattr(response, "output", []):
            history_item = _response_item_to_history(item)
            if history_item is not None:
                conversation.append(history_item)

        if not tool_calls:
            final_text = getattr(response, "output_text", "") or ""
            emit(f"最终结果：{final_text}")
            return final_text

        for item in tool_calls:
            try:
                arguments = json.loads(getattr(item, "arguments", "{}"))
            except json.JSONDecodeError as exc:
                result = f"错误：工具参数不是有效 JSON：{exc}"
                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": item.call_id,
                        "output": result,
                    }
                )
                continue

            result = _call_tool(item.name, arguments, workspace_root)
            conversation.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": result,
                }
            )

    raise RuntimeError("Exceeded max agent steps")


def run_agent(
    task: str,
    *,
    workspace_root: Path,
    client: Any | None = None,
    settings: Settings | None = None,
    logger: Callable[[str], None] | None = print,
) -> str:
    conversation: list[dict[str, Any]] = [{"role": "user", "content": task}]
    return _run_conversation(
        conversation,
        workspace_root=workspace_root,
        client=client,
        settings=settings,
        logger=logger,
    )


def run_chat_session(
    *,
    workspace_root: Path,
    client: Any | None = None,
    settings: Settings | None = None,
    logger: Callable[[str], None] | None = print,
    input_fn: Callable[[str], str] = input,
) -> None:
    settings = settings or load_settings()
    client = client or build_client(settings)
    workspace_root = workspace_root.resolve()
    emit = logger or (lambda _: None)
    sessions_index_path = _sessions_index_file(workspace_root)
    sessions = _load_sessions_index(sessions_index_path)
    legacy_conversation_path = _conversation_file(workspace_root)

    if not sessions and legacy_conversation_path.exists():
        conversation = _load_conversation(legacy_conversation_path)
        if conversation:
            active_session = _create_session_record("迁移会话")
            active_session["message_count"] = len(conversation)
            _save_conversation(_session_path(workspace_root, active_session["id"]), conversation)
            sessions = [active_session]
            _save_sessions_index(sessions_index_path, sessions)
            _clear_conversation(legacy_conversation_path)

    emit("进入对话模式，输入 /exit 退出，/reset 清空历史，/choose 选择对话")

    active_session = _create_session_record()
    active_session_path = _session_path(workspace_root, str(active_session["id"]))
    conversation: list[dict[str, Any]] = []
    active_session_persisted = False

    while True:
        try:
            user_text = input_fn("你> ").strip()
        except EOFError:
            break
        except KeyboardInterrupt:
            break

        if not user_text:
            continue
        if user_text in {"/exit", "exit", "quit", "/quit"}:
            if active_session_persisted or conversation:
                sessions = _sync_session_state(
                    sessions_index_path=sessions_index_path,
                    sessions=sessions,
                    active_session=active_session,
                    active_session_path=active_session_path,
                    conversation=conversation,
                    keep_empty=active_session_persisted,
                )
            break
        if user_text in {"/reset", "reset"}:
            conversation.clear()
            if active_session_persisted:
                sessions = _sync_session_state(
                    sessions_index_path=sessions_index_path,
                    sessions=sessions,
                    active_session=active_session,
                    active_session_path=active_session_path,
                    conversation=conversation,
                )
            continue
        if user_text in {"/new", "new"}:
            if active_session_persisted or conversation:
                sessions = _sync_session_state(
                    sessions_index_path=sessions_index_path,
                    sessions=sessions,
                    active_session=active_session,
                    active_session_path=active_session_path,
                    conversation=conversation,
                    keep_empty=active_session_persisted,
                )
            active_session = _create_session_record()
            active_session_path = _session_path(workspace_root, str(active_session["id"]))
            conversation = []
            active_session_persisted = False
            continue
        if user_text in {"/choose", "choose", "/switch", "switch"}:
            if active_session_persisted or conversation:
                sessions = _sync_session_state(
                    sessions_index_path=sessions_index_path,
                    sessions=sessions,
                    active_session=active_session,
                    active_session_path=active_session_path,
                    conversation=conversation,
                    keep_empty=active_session_persisted,
                )
            selected_session = _choose_session(sessions, input_fn, emit)
            if selected_session is None:
                continue
            existing_session = any(
                session.get("id") == selected_session.get("id")
                for session in sessions
            )
            active_session = selected_session
            active_session_path = _session_path(workspace_root, str(active_session["id"]))
            conversation = _load_conversation(active_session_path) if existing_session else []
            active_session_persisted = existing_session
            if existing_session:
                active_session["message_count"] = len(conversation)
                _print_conversation_history(conversation, emit)
            continue

        if _should_title_from_first_message(active_session):
            active_session["title"] = _derive_session_title(user_text)
            active_session["updated_at"] = time.time()
            sessions = _update_session_index(sessions, active_session)
            _save_sessions_index(sessions_index_path, sessions)

        conversation.append({"role": "user", "content": user_text})

        try:
            _run_conversation(
                conversation,
                workspace_root=workspace_root,
                client=client,
                settings=settings,
                logger=logger,
            )
        except RuntimeError as exc:
            emit(f"最终结果：错误：{exc}")

        sessions = _sync_session_state(
            sessions_index_path=sessions_index_path,
            sessions=sessions,
            active_session=active_session,
            active_session_path=active_session_path,
            conversation=conversation,
        )
        active_session_persisted = True
