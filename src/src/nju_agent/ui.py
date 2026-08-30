from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Iterator

from rich import box
from rich.console import Console
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

        if text in {"可用会话：", "权限选项："}:
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
            self.console.print(f"[bold cyan]你[/bold cyan]：{content}")
            return
        if label == "助手":
            self.console.print(f"[bold white]助手[/bold white]：{content}")
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
            Panel.fit(
                panel_content,
                title=title,
                border_style=border_style,
                box=box.ROUNDED,
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
            Panel.fit(
                renderable,
                title="工具结果",
                border_style="grey50",
                box=box.ROUNDED,
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
            Panel.fit(
                Text(content or "（空）", style=style),
                title=title,
                border_style=border_style,
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )


def create_terminal_ui() -> TerminalUI:
    return TerminalUI()
