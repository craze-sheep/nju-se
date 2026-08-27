from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

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


def run_agent(
    task: str,
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

    emit(f"用户任务：{task}")

    response = None
    previous_response_id: str | None = None
    model_input: Any = task

    for _ in range(settings.max_steps):
        response = request_response(
            client,
            model=settings.model,
            input=model_input,
            tools=tool_definitions(),
            instructions=SYSTEM_PROMPT,
            previous_response_id=previous_response_id,
        )

        tool_calls = [
            item
            for item in getattr(response, "output", [])
            if getattr(item, "type", None) == "function_call"
        ]
        if not tool_calls:
            final_text = getattr(response, "output_text", "") or ""
            emit(f"最终结果：{final_text}")
            return final_text

        model_input = []
        previous_response_id = getattr(response, "id", None)

        for item in tool_calls:
            arguments = json.loads(getattr(item, "arguments", "{}"))
            emit(f"工具调用：{item.name}")
            result = _call_tool(item.name, arguments, workspace_root)
            emit(f"工具结果：{result}")
            model_input.append(
                {
                    "type": "function_call_output",
                    "call_id": item.call_id,
                    "output": result,
                }
            )

    raise RuntimeError("Exceeded max agent steps")
