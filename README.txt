软件工程专业推免项目：构建编程智能体

仓库地址：https://github.com/craze-sheep/Semacode-Agent

Semacode Agent（析码智能体）是带有UI的命令行 coding agent，不依赖现成 agent 框架。模型只负责决定下一步做什么，文件读写、命令执行、会话管理和记忆整理都由本地程序完成。

运行方式：
1. 设置环境变量 `DEEPSEEK_API_KEY`
2. 在仓库根目录执行：
```bash
PYTHONPATH=src/src python -m nju_agent
```

特色功能：
- 本地工具：`search`、`list_files`、`read_file`、`write_file`、`run_command`
- 对话管理：支持多轮对话持久化、历史会话选择、上下文压缩
- 全局记忆：每次会话结束后自动生成摘要并合并到全局记忆
- Git 集成：`/diff` 查看最近一次写入，`/undo` 撤销最近一批写入
- 权限控制：默认只读，切到可写后才允许写文件和执行命令
- subagents：支持 planner / reviewer 轻量分工
- 安全保障：像 rm、git clean 这类危险命令执行前会要求确认
- UI 反馈：长任务期间会显示阶段状态和工具执行结果

常用命令：
- `/access`：在只读和可写之间切换
- `/subagents`：开启或关闭 planner / reviewer 分工
- `/diff`：查看最近一次写文件留下的差异
- `/undo`：撤销最近一批写入
- `/choose`：切换到已有历史会话
- `/reset`：清空当前会话
- `/new`：新建一个会话
- `/exit`：退出程序
