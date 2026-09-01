from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Iterator

from rich import box
from rich.console import Console, Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text


@dataclass
class TerminalUI:
    console: Console = field(
        default_factory=lambda: Console(highlight=False)
    )

    def banner(
        self,
        *,
        workspace_root: Path,
        model: str,
    ) -> None:
        info = Table.grid(padding=(0, 1))
        info.add_column(style="dim", no_wrap=True)
        info.add_column()
        info.add_row("工作区", str(workspace_root))
        info.add_row("模型", model)
        info.add_row("命令", "/access  /subagents  /diff  /undo  /choose  /reset  /exit")
        info.add_row("提示", "输入 /exit 退出，/reset 清空历史，/choose 选择对话，/access 切换权限")

        self.console.print(
            Panel(
                info,
                title="[bold cyan]Semacode Agent[/bold cyan]",
                subtitle="思考符号，理解代码",
                border_style="cyan",
                box=box.ROUNDED,
                expand=True,
                padding=(0, 1),
            )
        )

    def render_state(self, *, access_mode: str, subagents_enabled: bool) -> None:
        state = Text()
        state.append("编辑权限 ", style="dim")
        state.append(access_mode, style="cyan" if access_mode == "只读" else "green")
        state.append("  ·  ", style="dim")
        state.append("subagents ", style="dim")
        state.append("开启" if subagents_enabled else "关闭", style="magenta" if subagents_enabled else "yellow")
        self.console.print(state)

    def render_session_picker(self, entries: list[dict[str, object]]) -> None:
        body = Table.grid(expand=True, padding=(0, 0))
        body.add_column()

        if not entries:
            body.add_row(Text("没有可用会话，输入 n 新建。", style="dim"))
        else:
            for index, entry in enumerate(entries):
                body.add_row(self._render_session_entry(entry))
                if index < len(entries) - 1:
                    body.add_row(Text(""))

        hint = Text("输入编号切换，n 新建，b 返回", style="dim")
        self.console.print(
            Panel(
                Group(body, hint),
                title="[bold cyan]历史会话[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
                expand=True,
                padding=(0, 1),
            )
        )

    def render_conversation_history(self, conversation: list[dict[str, object]]) -> None:
        body_items: list[object] = []

        for item in conversation:
            item_type = str(item.get("type", "")).strip()
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", item.get("output", ""))).strip()

            if item_type == "function_call":
                name = str(item.get("name", "")).strip()
                arguments = str(item.get("arguments", "")).strip()
                content = f"{name} {arguments}".strip()
                label = "工具调用"
                style = "yellow"
            elif item_type == "function_call_output":
                content = str(item.get("output", "")).strip()
                label = "工具结果"
                style = "grey70"
            elif role == "user":
                label = "你"
                style = "bold cyan"
            elif role == "assistant":
                label = "助手"
                style = "bold white"
            else:
                continue

            if not content:
                continue

            if body_items:
                body_items.append(Text(""))
            body_items.append(Text(f"{label}：", style=style))
            if item_type == "function_call":
                body_items.append(Text(content))
            elif item_type == "function_call_output":
                body_items.append(self._render_history_output(content))
            elif role == "assistant":
                body_items.append(Markdown(content or "（空）"))
            else:
                body_items.append(Text(content))

        body: object = Group(*body_items) if body_items else Text("（空）", style="dim")

        self.console.print(
            Panel(
                body,
                title="[bold cyan]历史会话[/bold cyan]",
                border_style="cyan",
                box=box.ROUNDED,
                expand=True,
                padding=(0, 1),
            )
        )

    def input(self, prompt: str) -> str:
        return self.console.input(prompt)

    @contextmanager
    def status(self, message: str, spinner: str = "dots") -> Iterator[None]:
        with self.console.status(message, spinner=spinner):
            yield

    def emit(self, message: str) -> None:
        text = str(message).strip()
        if not text:
            return

        if text == "可用会话：":
            self.console.print(Rule(text, style="cyan"))
            return

        label, sep, content = text.partition("：")
        if not sep:
            self.console.print(text)
            return

        content = content.strip()

        if label == "规划":
            self._render_markdown_panel("规划", content, "cyan")
            return
        if label == "审查":
            self._render_markdown_panel("审查", content, "magenta")
            return
        if label == "审查问题":
            self._render_markdown_panel("审查问题", content, "yellow")
            return
        if label == "审查建议重试":
            self._render_markdown_panel("审查建议重试", content, "yellow")
            return
        if label == "危险命令":
            self.console.print(Text(f"{label}：{content}", style="bold red"))
            return
        if label == "确认执行":
            self.console.print(Text(f"{label}：{content}", style="red"))
            return
        if label == "最终结果":
            self._render_markdown_panel("最终结果", content, "green", bold=True)
            return
        if label == "工具调用":
            self._render_text_panel("工具调用", content, "yellow")
            return
        if label == "工具结果":
            self._render_tool_result_panel(content)
            return
        if label == "你":
            self._render_text_panel("你", content, "cyan")
            return
        if label == "助手":
            self._render_markdown_panel("助手", content, "white")
            return
        if label in {"当前权限", "当前分工"}:
            self.console.print(f"[dim]{label}：{content}[/dim]")
            return

        self.console.print(text)

    def _render_markdown_panel(
        self,
        title: str,
        content: str,
        border_style: str,
        *,
        bold: bool = False,
    ) -> None:
        panel_content = Markdown(content or "（空）")
        if bold:
            panel_content = Text.from_markup(f"[bold]{content or '（空）'}[/bold]")
        self.console.print(
            Panel(
                panel_content,
                title=title,
                border_style=border_style,
                box=box.ROUNDED,
                expand=True,
                padding=(0, 1),
            )
        )

    def _render_tool_result_panel(self, content: str) -> None:
        renderable: object = Text(content or "（空）", style="grey70")
        text = content.strip()
        if text:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(data, (dict, list)):
                    renderable = Pretty(data, expand_all=True, max_depth=6)

        self.console.print(
            Panel(
                renderable,
                title="工具结果",
                border_style="grey50",
                box=box.ROUNDED,
                expand=True,
                padding=(0, 1),
            )
        )

    def _render_text_panel(
        self,
        title: str,
        content: str,
        border_style: str,
        *,
        bold: bool = False,
    ) -> None:
        style = "bold " + border_style if bold else border_style
        self.console.print(
            Panel(
                Text(content or "（空）", style=style),
                title=title,
                border_style=border_style,
                box=box.ROUNDED,
                expand=True,
                padding=(0, 1),
            )
        )

    def _render_session_entry(self, entry: dict[str, object]) -> Text:
        index = str(entry.get("index", "")).strip()
        title = str(entry.get("title", "")).strip() or "未命名会话"
        current = bool(entry.get("current", False))
        updated_at = str(entry.get("updated_at", "")).strip()
        message_count = str(entry.get("message_count", "")).strip()
        status = str(entry.get("status", "")).strip()
        preview = str(entry.get("preview", "")).strip()

        text = Text()
        text.append(f"{index}. {title}", style="bold cyan" if current else "bold")
        if current:
            text.append("  当前", style="magenta")
        text.append("\n")

        meta_parts = [part for part in [updated_at, message_count, status] if part]
        if meta_parts:
            text.append(" · ".join(meta_parts), style="dim")
        if preview:
            text.append("\n")
            text.append(f"最近：{preview}", style="white")
        return text

    def _render_history_output(self, content: str) -> object:
        text = content.strip()
        if not text:
            return Text("（空）", style="dim")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return Text(text, style="grey70")
        if isinstance(data, (dict, list)):
            return Pretty(data, expand_all=True, max_depth=4)
        return Text(text, style="grey70")


def create_terminal_ui() -> TerminalUI:
    return TerminalUI()
