from __future__ import annotations

from copy import deepcopy
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import tiktoken

from .config import Settings, load_settings
from .llm import build_client, request_response
from .tools import list_files, read_file, run_command, revert_write_file, write_file


SYSTEM_PROMPT = """You are a coding agent.
Use the available tools to complete the user's task.
Keep file operations inside the workspace root.
When you finish, answer briefly in Chinese."""

ACCESS_READ_ONLY = "read_only"
ACCESS_WRITE = "write"

SESSION_SUMMARY_PROMPT = """你是一个会话摘要器。请根据下面的完整对话，提炼出简短、结构化、可用于后续记忆更新的摘要。

要求：
1. 只保留对后续有用的信息，不要复述原文。
2. 优先提炼：任务目标、已确认决定、重要文件、未完成事项、用户偏好。
3. 如果没有明确内容，就留空，不要编造。
4. 输出尽量简洁，适合给后续记忆合并模型使用。

输出格式：
```json
{
  "goal": "",
  "decisions": [],
  "important_files": [],
  "open_tasks": [],
  "user_preferences": [],
  "notes": []
}
```"""

SESSION_MEMORY_UPDATE_PROMPT = """你是一个会话记忆更新器。请把“当前会话记忆”和“新增历史片段”合并成一份更新后的会话记忆。

要求：
1. 只保留对后续有用的信息，不要复述原文。
2. 优先保留：任务目标、已确认决定、重要文件、未完成事项、用户偏好。
3. 如果有冲突，优先保留更稳定、更明确、更长期有效的内容。
4. 不要保留流水账，不要保留原始对话。
5. 输出必须是严格 JSON，字段结构保持不变。

输出格式：
```json
{
  "goal": "",
  "decisions": [],
  "important_files": [],
  "open_tasks": [],
  "user_preferences": [],
  "notes": []
}
```"""

GLOBAL_MEMORY_MERGE_PROMPT = """你是一个全局记忆合并器。请把“现有全局 `.md`”和“本会话摘要”合并成一份新的全局 `.md`。

要求：
1. 只保留长期稳定、可复用、低歧义的信息。
2. 去重、合并同义项、删除过时或冲突内容。
3. 如果新信息和旧 memory 冲突，优先保留更稳定、更明确、更长期有效的内容。
4. 不要保留流水账，不要保留原始对话。
5. 输出要短、清晰、适合下次对话直接注入。

输出格式：
```markdown
# Global Memory

## User Preferences
- ...

## Project Rules
- ...

## Stable Decisions
- ...

## Common Pitfalls
- ...
```"""


def _normalize_access_mode(value: Any) -> str:
    mode = str(value or "").strip().lower()
    if mode in {ACCESS_READ_ONLY, "readonly", "read-only", "read"}:
        return ACCESS_READ_ONLY
    return ACCESS_WRITE


def _access_mode_label(access_mode: str) -> str:
    return "只读" if _normalize_access_mode(access_mode) == ACCESS_READ_ONLY else "可写"


def _can_use_write_tools(access_mode: str) -> bool:
    return _normalize_access_mode(access_mode) == ACCESS_WRITE


def tool_definitions(access_mode: str = ACCESS_READ_ONLY) -> list[dict[str, Any]]:
    tools = [
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
    ]
    if _can_use_write_tools(access_mode):
        tools.extend(
            [
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
        )
    return tools

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


def _memory_dir(workspace_root: Path) -> Path:
    return workspace_root / ".nju_agent" / "memory"


def _session_memory_file(workspace_root: Path, session_id: str) -> Path:
    return _memory_dir(workspace_root) / f"{session_id}.json"


def _global_memory_file(workspace_root: Path) -> Path:
    return workspace_root / ".nju_agent" / "global_memory.md"


def _finalizer_snapshot_dir(workspace_root: Path) -> Path:
    return workspace_root / ".nju_agent" / "finalizer_snapshots"


def _finalizer_snapshot_file(workspace_root: Path, session_id: str) -> Path:
    return _finalizer_snapshot_dir(workspace_root) / f"{session_id}.json"


def _write_batches_dir(workspace_root: Path) -> Path:
    return workspace_root / ".nju_agent" / "write_batches"


def _write_batches_file(workspace_root: Path, session_id: str) -> Path:
    return _write_batches_dir(workspace_root) / f"{session_id}.json"


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


def _load_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _save_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _load_json_file(path: Path, default: Any) -> Any:
    raw = _load_text_file(path)
    if not raw:
        return default
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return default
    return data if data is not None else default


def _save_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_finalizer_snapshot(
    workspace_root: Path,
    session_snapshot: dict[str, Any],
    conversation_snapshot: list[dict[str, Any]],
    keep_empty: bool,
) -> Path:
    snapshot = {
        "workspace_root": str(workspace_root),
        "session_snapshot": session_snapshot,
        "conversation_snapshot": conversation_snapshot,
        "keep_empty": keep_empty,
    }
    path = _finalizer_snapshot_file(workspace_root, str(session_snapshot["id"]))
    _save_json_file(path, snapshot)
    return path


def _load_finalizer_snapshot(path: Path) -> dict[str, Any]:
    raw = _load_text_file(path)
    if not raw:
        raise RuntimeError("finalizer snapshot is empty")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("finalizer snapshot must be a JSON object")
    return data


def _finalize_snapshot_file(snapshot_path: Path) -> None:
    data = _load_finalizer_snapshot(snapshot_path)
    workspace_root = Path(str(data.get("workspace_root", ""))).resolve()
    session_snapshot = data.get("session_snapshot", {})
    conversation_snapshot = data.get("conversation_snapshot", [])
    keep_empty = bool(data.get("keep_empty", False))

    if not isinstance(session_snapshot, dict):
        raise RuntimeError("finalizer snapshot session data is invalid")
    if not isinstance(conversation_snapshot, list):
        raise RuntimeError("finalizer snapshot conversation data is invalid")

    session_id = str(session_snapshot.get("id", "")).strip()
    if not session_id:
        raise RuntimeError("finalizer snapshot session id is missing")

    settings = load_settings()
    client = build_client(settings)
    _sync_session_state(
        sessions_index_path=_sessions_index_file(workspace_root),
        sessions=_load_sessions_index(_sessions_index_file(workspace_root)),
        active_session=session_snapshot,
        active_session_path=_session_path(workspace_root, session_id),
        conversation=conversation_snapshot,
        keep_empty=keep_empty,
    )
    _finalize_session_memory(
        workspace_root=workspace_root,
        session_id=session_id,
        conversation=conversation_snapshot,
        client=client,
        settings=settings,
    )


def _spawn_detached_finalizer(snapshot_path: Path) -> subprocess.Popen[Any]:
    data = _load_finalizer_snapshot(snapshot_path)
    workspace_root = Path(str(data.get("workspace_root", ""))).resolve()
    return subprocess.Popen(
        [sys.executable, "-m", "nju_agent", "--finalize-snapshot", str(snapshot_path)],
        cwd=str(workspace_root),
        env=os.environ.copy(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def _load_write_batches(workspace_root: Path, session_id: str) -> list[dict[str, Any]]:
    data = _load_json_file(_write_batches_file(workspace_root, session_id), [])
    return data if isinstance(data, list) else []


def _save_write_batches(
    workspace_root: Path,
    session_id: str,
    batches: list[dict[str, Any]],
) -> None:
    _save_json_file(_write_batches_file(workspace_root, session_id), batches)


def _record_write_batch(
    workspace_root: Path,
    session_id: str,
    changes: list[dict[str, Any]],
) -> None:
    if not changes:
        return
    batches = _load_write_batches(workspace_root, session_id)
    batches.append(
        {
            "id": uuid4().hex,
            "created_at": time.time(),
            "changes": changes,
        }
    )
    _save_write_batches(workspace_root, session_id, batches)


def _format_write_batch_diff(batch: dict[str, Any]) -> str:
    changes = batch.get("changes", [])
    if not isinstance(changes, list) or not changes:
        return "最近一批 write_file 没有记录到文件差异"

    parts: list[str] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        diff = str(change.get("diff", "")).strip()
        relative_path = str(change.get("relative_path", "")).strip()
        if diff:
            parts.append(diff)
        elif relative_path:
            parts.append(f"{relative_path} 没有文本差异")
    return "\n\n".join(parts) if parts else "最近一批 write_file 没有记录到文件差异"


def _last_write_diff(workspace_root: Path, session_id: str) -> str:
    batches = _load_write_batches(workspace_root, session_id)
    if not batches:
        return "没有可查看的 write_file 差异"
    return _format_write_batch_diff(batches[-1])


def _can_git_undo_change(change: dict[str, Any]) -> bool:
    if not isinstance(change, dict):
        return False
    relative_path = str(change.get("relative_path", "")).strip()
    if not relative_path:
        return False
    tracked_before = bool(change.get("tracked_before", False))
    existed_before = bool(change.get("existed_before", False))
    return tracked_before or not existed_before


def _undo_last_write_batch(workspace_root: Path, session_id: str) -> str:
    batches = _load_write_batches(workspace_root, session_id)
    if not batches:
        return "没有可撤销的 write_file 操作"

    batch = batches[-1]
    changes = batch.get("changes", [])
    if not isinstance(changes, list) or not changes:
        return "最近一批 write_file 没有可撤销的文件"

    unsupported = [
        str(change.get("relative_path", "")).strip()
        for change in changes
        if isinstance(change, dict) and not _can_git_undo_change(change)
    ]
    if unsupported:
        return f"最近一批 write_file 里有 Git 无法直接撤销的文件：{', '.join(filter(None, unsupported))}"

    try:
        for change in reversed(changes):
            if isinstance(change, dict):
                revert_write_file(str(workspace_root), change)
    except RuntimeError as exc:
        return f"撤销失败：{exc}"

    batches.pop()
    _save_write_batches(workspace_root, session_id, batches)
    return f"已撤销最近一批 write_file 操作，共 {len(changes)} 个文件"


def _default_session_memory() -> dict[str, Any]:
    return {
        "goal": "",
        "decisions": [],
        "important_files": [],
        "open_tasks": [],
        "user_preferences": [],
        "notes": [],
    }


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def _normalize_session_memory(data: Any) -> dict[str, Any]:
    base = _default_session_memory()
    if not isinstance(data, dict):
        return base
    base["goal"] = str(data.get("goal", "")).strip()
    base["decisions"] = _normalize_string_list(data.get("decisions", []))
    base["important_files"] = _normalize_string_list(data.get("important_files", []))
    base["open_tasks"] = _normalize_string_list(data.get("open_tasks", []))
    base["user_preferences"] = _normalize_string_list(data.get("user_preferences", []))
    base["notes"] = _normalize_string_list(data.get("notes", []))
    return base


def _session_memory_markdown(memory: dict[str, Any]) -> str:
    lines = ["# Session Memory", ""]
    goal = str(memory.get("goal", "")).strip()
    lines.extend(["## Goal", f"- {goal or '（空）'}", ""])
    for key, title in [
        ("decisions", "Decisions"),
        ("important_files", "Important Files"),
        ("open_tasks", "Open Tasks"),
        ("user_preferences", "User Preferences"),
        ("notes", "Notes"),
    ]:
        lines.append(f"## {title}")
        items = _normalize_string_list(memory.get(key, []))
        if items:
            lines.extend([f"- {item}" for item in items])
        else:
            lines.append("- （空）")
        lines.append("")
    return "\n".join(lines).strip()


def _global_memory_markdown(workspace_root: Path) -> str:
    raw = _load_text_file(_global_memory_file(workspace_root)).strip()
    if raw:
        return raw
    return "# Global Memory\n\n## User Preferences\n- （空）\n\n## Project Rules\n- （空）\n\n## Stable Decisions\n- （空）\n\n## Common Pitfalls\n- （空）"


def _load_session_memory(workspace_root: Path, session_id: str) -> dict[str, Any]:
    return _normalize_session_memory(
        _load_json_file(_session_memory_file(workspace_root, session_id), _default_session_memory())
    )


def _save_session_memory(
    workspace_root: Path,
    session_id: str,
    session_memory: dict[str, Any],
) -> None:
    _save_json_file(_session_memory_file(workspace_root, session_id), _normalize_session_memory(session_memory))


def _session_compacted_upto(session: dict[str, Any]) -> int:
    return max(0, int(session.get("memory_compacted_upto", 0) or 0))


def _set_session_compacted_upto(session: dict[str, Any], value: int) -> None:
    session["memory_compacted_upto"] = max(0, int(value))


def _compaction_cutoff(conversation: list[dict[str, Any]], recent_turns: int) -> int:
    if not conversation:
        return 0

    user_positions = [
        index
        for index, item in enumerate(conversation)
        if str(item.get("role", "")).strip() == "user"
    ]
    if len(user_positions) <= recent_turns:
        return 0
    return user_positions[-recent_turns]


def _tokenizer_for_model(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


@lru_cache(maxsize=32)
def _cached_encoding(model: str):
    return _tokenizer_for_model(model)


def _count_tokens(text: str, model: str) -> int:
    if not text:
        return 0
    try:
        return len(_cached_encoding(model).encode(text))
    except Exception:
        return max(1, len(text) // 4)


def _count_payload_tokens(
    *,
    instructions: str,
    conversation: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
) -> int:
    payload = {
        "instructions": instructions,
        "conversation": conversation,
        "tools": tools,
    }
    return _count_tokens(json.dumps(payload, ensure_ascii=False, sort_keys=True), model)


def _conversation_to_transcript(conversation: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for item in conversation:
        item_type = str(item.get("type", "")).strip()
        role = str(item.get("role", "")).strip()
        if item_type == "function_call":
            lines.append(
                "工具调用："
                f"{item.get('name', '')} {item.get('arguments', '')}"
            )
        elif item_type == "function_call_output":
            lines.append(f"工具结果：{item.get('output', '')}")
        elif role == "user":
            lines.append(f"用户：{item.get('content', '')}")
        elif role == "assistant":
            lines.append(f"助手：{item.get('content', '')}")
    return "\n".join(lines).strip()


def _visible_conversation(
    conversation: list[dict[str, Any]],
    recent_turns: int,
) -> list[dict[str, Any]]:
    if recent_turns <= 0 or not conversation:
        return []

    user_positions = [
        index
        for index, item in enumerate(conversation)
        if str(item.get("role", "")).strip() == "user"
    ]
    if len(user_positions) <= recent_turns:
        return list(conversation)

    start_index = user_positions[-recent_turns]
    return list(conversation[start_index:])


def _build_instructions(
    *,
    workspace_root: Path,
    session_memory: dict[str, Any],
    access_mode: str,
) -> str:
    global_memory = _global_memory_markdown(workspace_root)
    session_memory_text = _session_memory_markdown(session_memory)
    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"当前会话权限：{_access_mode_label(access_mode)}\n\n"
        f"全局记忆：\n{global_memory}\n\n"
        f"会话记忆：\n{session_memory_text}"
    )


def _fit_visible_conversation(
    *,
    conversation: list[dict[str, Any]],
    workspace_root: Path,
    settings: Settings,
    session_memory: dict[str, Any],
    access_mode: str,
) -> tuple[list[dict[str, Any]], int]:
    instructions = _build_instructions(
        workspace_root=workspace_root,
        session_memory=session_memory,
        access_mode=access_mode,
    )
    max_turns = min(settings.recent_turns, len(
        [item for item in conversation if str(item.get("role", "")).strip() == "user"]
    ))
    max_turns = max(max_turns, 1)

    for turns in range(max_turns, 0, -1):
        visible = _visible_conversation(conversation, turns)
        token_count = _count_payload_tokens(
            instructions=instructions,
            conversation=visible,
            tools=tool_definitions(access_mode),
            model=settings.model,
        )
        if token_count <= settings.context_token_limit or turns == 1:
            return visible, token_count

    return list(conversation), _count_payload_tokens(
        instructions=instructions,
        conversation=conversation,
        tools=tool_definitions(access_mode),
        model=settings.model,
    )


def _summarize_session_memory(
    *,
    conversation: list[dict[str, Any]],
    client: Any,
    settings: Settings,
) -> dict[str, Any]:
    transcript = _conversation_to_transcript(conversation)
    if not transcript:
        return _default_session_memory()

    response = request_response(
        client,
        model=settings.model,
        input=[{"role": "user", "content": transcript}],
        tools=[],
        instructions=SESSION_SUMMARY_PROMPT,
    )
    text = getattr(response, "output_text", "") or ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _default_session_memory()
    return _normalize_session_memory(data)


def _update_session_memory_incrementally(
    *,
    current_memory: dict[str, Any],
    new_conversation_chunk: list[dict[str, Any]],
    client: Any,
    settings: Settings,
) -> dict[str, Any]:
    chunk_text = _conversation_to_transcript(new_conversation_chunk)
    if not chunk_text:
        return current_memory

    response = request_response(
        client,
        model=settings.model,
        input=[
            {
                "role": "user",
                "content": (
                    f"当前会话记忆：\n{_session_memory_markdown(current_memory)}\n\n"
                    f"新增历史片段：\n{chunk_text}"
                ),
            }
        ],
        tools=[],
        instructions=SESSION_MEMORY_UPDATE_PROMPT,
    )
    text = getattr(response, "output_text", "") or ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return current_memory
    return _normalize_session_memory(data)


def _merge_global_memory(
    *,
    workspace_root: Path,
    session_memory: dict[str, Any],
    client: Any,
    settings: Settings,
) -> str:
    current_global = _global_memory_markdown(workspace_root)
    session_memory_text = _session_memory_markdown(session_memory)
    response = request_response(
        client,
        model=settings.model,
        input=[
            {
                "role": "user",
                "content": (
                    f"现有全局 `.md`：\n{current_global}\n\n"
                    f"本会话摘要：\n{session_memory_text}"
                ),
            }
        ],
        tools=[],
        instructions=GLOBAL_MEMORY_MERGE_PROMPT,
    )
    return (getattr(response, "output_text", "") or "").strip() or current_global


def _compact_session_memory_if_needed(
    *,
    workspace_root: Path,
    active_session: dict[str, Any],
    conversation: list[dict[str, Any]],
    session_memory: dict[str, Any],
    client: Any,
    settings: Settings,
) -> dict[str, Any]:
    compacted_upto = _session_compacted_upto(active_session)
    cutoff = _compaction_cutoff(conversation, settings.recent_turns)
    if cutoff <= compacted_upto:
        return session_memory

    chunk = conversation[compacted_upto:cutoff]
    if not chunk:
        return session_memory

    chunk_tokens = _count_tokens(_conversation_to_transcript(chunk), settings.model)
    if chunk_tokens < settings.context_token_limit:
        return session_memory

    updated_memory = _update_session_memory_incrementally(
        current_memory=session_memory,
        new_conversation_chunk=chunk,
        client=client,
        settings=settings,
    )
    _save_session_memory(
        workspace_root,
        str(active_session["id"]),
        updated_memory,
    )
    _set_session_compacted_upto(active_session, cutoff)
    active_session["updated_at"] = time.time()
    return updated_memory


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
        "memory_compacted_upto": 0,
        "access_mode": ACCESS_READ_ONLY,
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


def _choose_access_mode(
    input_fn: Callable[[str], str],
    logger: Callable[[str], None],
) -> str | None:
    emit = logger or (lambda _: None)
    emit("权限选项：")
    emit("1. 只读")
    emit("2. 可写")
    emit("b. 返回")

    while True:
        choice = input_fn("选择权限编号，或输入 b 返回：").strip().lower()
        if choice in {"b", "back"}:
            return None
        if choice == "1":
            return ACCESS_READ_ONLY
        if choice == "2":
            return ACCESS_WRITE
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


def _session_access_mode(session: dict[str, Any]) -> str:
    return _normalize_access_mode(session.get("access_mode", ACCESS_READ_ONLY))


def _set_session_access_mode(session: dict[str, Any], access_mode: str) -> None:
    session["access_mode"] = _normalize_access_mode(access_mode)


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


def _call_tool(
    name: str,
    arguments: dict[str, Any],
    workspace_root: Path,
    access_mode: str,
    write_changes: list[dict[str, Any]] | None = None,
) -> str:
    root = str(workspace_root)

    try:
        if name == "list_files":
            return json.dumps(list_files(root), ensure_ascii=False)
        if name == "read_file":
            return read_file(root, arguments["relative_path"])
        if name == "write_file":
            if not _can_use_write_tools(access_mode):
                return "错误：当前会话是只读权限，不能使用 write_file"
            result = write_file(root, arguments["relative_path"], arguments["content"])
            change = {
                "relative_path": result.relative_path,
                "existed_before": result.existed_before,
                "tracked_before": result.tracked_before,
                "diff": result.diff,
            }
            if write_changes is not None:
                write_changes.append(change)
            return _format_tool_result(
                name,
                {
                    "status": "success",
                    "relative_path": result.relative_path,
                    "diff": result.diff,
                },
            )
        if name == "run_command":
            if not _can_use_write_tools(access_mode):
                return "错误：当前会话是只读权限，不能使用 run_command"
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
    session_memory: dict[str, Any] | None = None,
    access_mode: str = ACCESS_WRITE,
    write_changes: list[dict[str, Any]] | None = None,
    logger: Callable[[str], None] | None = print,
) -> str:
    settings = settings or load_settings()
    client = client or build_client(settings)
    workspace_root = workspace_root.resolve()
    session_memory = session_memory or _default_session_memory()
    emit = logger or (lambda _: None)

    response = None

    for _ in range(settings.max_steps):
        visible_conversation, _ = _fit_visible_conversation(
            conversation=conversation,
            workspace_root=workspace_root,
            settings=settings,
            session_memory=session_memory,
            access_mode=access_mode,
        )
        response = request_response(
            client,
            model=settings.model,
            input=visible_conversation,
            tools=tool_definitions(access_mode),
            instructions=_build_instructions(
                workspace_root=workspace_root,
                session_memory=session_memory,
                access_mode=access_mode,
            ),
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

            result = _call_tool(
                item.name,
                arguments,
                workspace_root,
                access_mode=access_mode,
                write_changes=write_changes,
            )
            conversation.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": result,
                }
            )

    raise RuntimeError("Exceeded max agent steps")


def _finalize_session_memory(
    *,
    workspace_root: Path,
    session_id: str,
    conversation: list[dict[str, Any]],
    client: Any,
    settings: Settings,
) -> dict[str, Any]:
    if not conversation:
        return _load_session_memory(workspace_root, session_id)

    session_memory = _summarize_session_memory(
        conversation=conversation,
        client=client,
        settings=settings,
    )
    _save_session_memory(workspace_root, session_id, session_memory)
    merged_global_memory = _merge_global_memory(
        workspace_root=workspace_root,
        session_memory=session_memory,
        client=client,
        settings=settings,
    )
    _save_text_file(_global_memory_file(workspace_root), merged_global_memory)
    return session_memory


def run_agent(
    task: str,
    *,
    workspace_root: Path,
    client: Any | None = None,
    settings: Settings | None = None,
    access_mode: str = ACCESS_READ_ONLY,
    logger: Callable[[str], None] | None = print,
) -> str:
    conversation: list[dict[str, Any]] = [{"role": "user", "content": task}]
    return _run_conversation(
        conversation,
        workspace_root=workspace_root,
        client=client,
        settings=settings,
        access_mode=access_mode,
        logger=logger,
    )


def run_chat_session(
    *,
    workspace_root: Path,
    client: Any | None = None,
    settings: Settings | None = None,
    logger: Callable[[str], None] | None = print,
    input_fn: Callable[[str], str] = input,
    background_finalize: bool = False,
) -> None:
    settings = settings or load_settings()
    client = client or build_client(settings)
    workspace_root = workspace_root.resolve()
    emit = logger or (lambda _: None)
    sessions_index_path = _sessions_index_file(workspace_root)
    sessions = _load_sessions_index(sessions_index_path)
    legacy_conversation_path = _conversation_file(workspace_root)
    exit_requested = False

    if not sessions and legacy_conversation_path.exists():
        conversation = _load_conversation(legacy_conversation_path)
        if conversation:
            active_session = _create_session_record("迁移会话")
            active_session["message_count"] = len(conversation)
            _save_conversation(_session_path(workspace_root, active_session["id"]), conversation)
            sessions = [active_session]
            _save_sessions_index(sessions_index_path, sessions)
            _clear_conversation(legacy_conversation_path)

    emit("进入对话模式，输入 /exit 退出，/reset 清空历史，/choose 选择对话，/access 切换权限，/diff 查看差异，/undo 撤销写入")

    active_session = _create_session_record()
    active_session_path = _session_path(workspace_root, str(active_session["id"]))
    conversation: list[dict[str, Any]] = []
    session_memory = _default_session_memory()
    active_session_persisted = False
    pending_finalizers: dict[str, Any] = {}
    emit(f"当前权限：{_access_mode_label(_session_access_mode(active_session))}，输入 /access 切换")

    def _wait_for_finalizer(session_id: str) -> None:
        thread = pending_finalizers.get(session_id)
        if thread is None:
            return
        wait = getattr(thread, "wait", None)
        if callable(wait):
            wait()
        else:
            thread.join()
        pending_finalizers.pop(session_id, None)

    def _wait_for_all_finalizers() -> None:
        for session_id in list(pending_finalizers.keys()):
            _wait_for_finalizer(session_id)

    def _finalize_snapshot(
        *,
        session_snapshot: dict[str, Any],
        conversation_snapshot: list[dict[str, Any]],
        keep_empty: bool,
    ) -> dict[str, Any]:
        if not conversation_snapshot:
            return _load_session_memory(workspace_root, str(session_snapshot["id"]))
        session_path = _session_path(workspace_root, str(session_snapshot["id"]))
        _sync_session_state(
            sessions_index_path=sessions_index_path,
            sessions=_load_sessions_index(sessions_index_path),
            active_session=session_snapshot,
            active_session_path=session_path,
            conversation=conversation_snapshot,
            keep_empty=keep_empty,
        )
        return _finalize_session_memory(
            workspace_root=workspace_root,
            session_id=str(session_snapshot["id"]),
            conversation=conversation_snapshot,
            client=client,
            settings=settings,
        )

    def finalize_current_session() -> None:
        nonlocal sessions, session_memory, active_session_persisted
        if not conversation:
            return
        _wait_for_finalizer(str(active_session["id"]))
        session_memory = _finalize_snapshot(
            session_snapshot=active_session,
            conversation_snapshot=conversation,
            keep_empty=active_session_persisted,
        )
        sessions = _load_sessions_index(sessions_index_path)
        active_session_persisted = True

    def maybe_compact_session_memory() -> None:
        nonlocal session_memory, sessions
        before = _session_compacted_upto(active_session)
        session_memory = _compact_session_memory_if_needed(
            workspace_root=workspace_root,
            active_session=active_session,
            conversation=conversation,
            session_memory=session_memory,
            client=client,
            settings=settings,
        )
        after = _session_compacted_upto(active_session)
        if after != before:
            sessions = _update_session_index(sessions, active_session)
            _save_sessions_index(sessions_index_path, sessions)

    while True:
        try:
            user_text = input_fn("你> ").strip()
        except EOFError:
            finalize_current_session()
            break
        except KeyboardInterrupt:
            finalize_current_session()
            break

        if not user_text:
            continue
        maybe_compact_session_memory()
        if user_text in {"/exit", "exit", "quit", "/quit"}:
            if background_finalize and conversation:
                _sync_session_state(
                    sessions_index_path=sessions_index_path,
                    sessions=sessions,
                    active_session=active_session,
                    active_session_path=active_session_path,
                    conversation=conversation,
                )
                snapshot_path = _save_finalizer_snapshot(
                    workspace_root,
                    deepcopy(active_session),
                    deepcopy(conversation),
                    active_session_persisted,
                )
                _spawn_detached_finalizer(snapshot_path)
                exit_requested = True
            else:
                finalize_current_session()
            break
        if user_text in {"/diff", "diff"}:
            emit(_last_write_diff(workspace_root, str(active_session["id"])))
            continue
        if user_text in {"/undo", "undo"}:
            emit(_undo_last_write_batch(workspace_root, str(active_session["id"])))
            continue
        if user_text in {"/access", "access", "/perm", "perm", "/mode", "mode"}:
            selected_mode = _choose_access_mode(input_fn, emit)
            if selected_mode is None:
                continue
            _set_session_access_mode(active_session, selected_mode)
            sessions = _sync_session_state(
                sessions_index_path=sessions_index_path,
                sessions=sessions,
                active_session=active_session,
                active_session_path=active_session_path,
                conversation=conversation,
            )
            emit(f"当前权限已切换为：{_access_mode_label(selected_mode)}")
            continue
        if user_text in {"/reset", "reset"}:
            finalize_current_session()
            conversation.clear()
            sessions = _sync_session_state(
                sessions_index_path=sessions_index_path,
                sessions=sessions,
                active_session=active_session,
                active_session_path=active_session_path,
                conversation=conversation,
                keep_empty=True,
            )
            _save_write_batches(workspace_root, str(active_session["id"]), [])
            session_memory = _default_session_memory()
            active_session_persisted = False
            continue
        if user_text in {"/new", "new"}:
            finalize_current_session()
            active_session = _create_session_record()
            active_session_path = _session_path(workspace_root, str(active_session["id"]))
            conversation = []
            session_memory = _default_session_memory()
            active_session_persisted = False
            continue
        if user_text in {"/choose", "choose", "/switch", "switch"}:
            selected_session = _choose_session(sessions, input_fn, emit)
            if selected_session is None:
                continue
            existing_session = any(
                session.get("id") == selected_session.get("id")
                for session in sessions
            )
            selected_session_id = str(selected_session.get("id", ""))
            if conversation and selected_session_id != str(active_session.get("id", "")):
                session_snapshot = deepcopy(active_session)
                conversation_snapshot = deepcopy(conversation)
                keep_empty_snapshot = active_session_persisted
                session_id_snapshot = str(session_snapshot["id"])

                thread = pending_finalizers.get(session_id_snapshot)
                if thread is None:
                    snapshot_path = _save_finalizer_snapshot(
                        workspace_root,
                        session_snapshot,
                        conversation_snapshot,
                        keep_empty_snapshot,
                    )
                    pending_finalizers[session_id_snapshot] = _spawn_detached_finalizer(
                        snapshot_path
                    )
            if selected_session_id:
                _wait_for_finalizer(selected_session_id)
            active_session = selected_session
            active_session_path = _session_path(workspace_root, str(active_session["id"]))
            conversation = _load_conversation(active_session_path) if existing_session else []
            active_session_persisted = existing_session
            _set_session_access_mode(active_session, _session_access_mode(active_session))
            session_memory = (
                _load_session_memory(workspace_root, str(active_session["id"]))
                if existing_session
                else _default_session_memory()
            )
            if existing_session:
                active_session["message_count"] = len(conversation)
                _print_conversation_history(conversation, emit)
            emit(f"当前权限：{_access_mode_label(_session_access_mode(active_session))}，输入 /access 切换")
            continue

        if _should_title_from_first_message(active_session):
            active_session["title"] = _derive_session_title(user_text)
            active_session["updated_at"] = time.time()
            sessions = _update_session_index(sessions, active_session)
            _save_sessions_index(sessions_index_path, sessions)

        conversation.append({"role": "user", "content": user_text})
        write_changes: list[dict[str, Any]] = []

        try:
            _run_conversation(
                conversation,
                workspace_root=workspace_root,
                client=client,
                settings=settings,
                session_memory=session_memory,
                access_mode=_session_access_mode(active_session),
                write_changes=write_changes,
                logger=logger,
            )
        except RuntimeError as exc:
            emit(f"最终结果：错误：{exc}")

        _record_write_batch(
            workspace_root,
            str(active_session["id"]),
            write_changes,
        )

        sessions = _sync_session_state(
            sessions_index_path=sessions_index_path,
            sessions=sessions,
            active_session=active_session,
            active_session_path=active_session_path,
            conversation=conversation,
        )
        active_session_persisted = True

    if not exit_requested:
        _wait_for_all_finalizers()
