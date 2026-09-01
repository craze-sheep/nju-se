NJU 推免考核项目：构建编程智能体

Semacode Agent（思码智能体）：以语义建模为内核的 coding agent，面向需求理解、代码生成、检索与修复，保持意图一致。

仓库地址：https://github.com/craze-sheep/nju-se.git

这是一个自写的 coding agent。它不依赖现成 agent 框架，而是基于 DeepSeek 原生 tool calling，由程序自己完成对话编排、本地工具执行、上下文管理、记忆维护和循环终止。它可以读取文件、修改文件、执行命令，并持续推进编程任务。

已实现功能：
- 终端交互式对话：用户直接在命令行输入任务，agent 会一轮一轮地接着处理，带有更清晰的阶段提示与过程展示。
- 原生 tool calling：模型不直接改文件或跑命令，而是先判断下一步要不要调用工具；真正的执行逻辑由本地程序接管。
- 本地工具：实现了 `search`、`list_files`、`read_file`、`write_file`、`run_command`，分别负责关键词检索、看目录、读文件、写文件和执行命令。
- 对话管理：程序会保存历史消息，还支持会话切换、最近轮数裁剪和 token 预算控制，避免上下文越来越长、最后装不下。
- 记忆系统：每个会话结束后都会生成摘要，再合并到全局记忆里，用来保留用户偏好、关键决定和重要文件。
- 权限控制：默认是只读；用户可以用 `/access` 切到可写。只读时开放 `search` / `list_files` / `read_file`，不会让模型直接修改内容。
- Git 集成：`write_file` 会记录 diff，用户可以用 `/diff` 看最近一次改了什么，用 `/undo` 撤销最近一批写入。
- 轻量分工：用户可以用 `/subagents` 打开 planner / reviewer。planner 先把任务拆清楚，reviewer 再检查结果，真正动手的还是 executor。
- 本地执行：`run_command` 直接在当前工作区里执行命令，遇到危险命令会先确认再跑。
- 错误处理：工具失败时不会让整个程序崩掉，而是把错误信息返回给模型继续处理。

这个版本的核心特点是：所有关键逻辑都在本地实现，模型只负责“想下一步做什么”，不负责直接碰文件或执行命令。

运行方式：
1. 设置环境变量 `DEEPSEEK_API_KEY`
2. 在仓库根目录执行：`PYTHONPATH=src/src python -m nju_agent`
3. 运行测试：`PYTHONPATH=src/src pytest src/tests -q`

补充说明：
- API key 只通过环境变量提供，不写入仓库、README.txt 或视频
- `run_command` 默认本地执行；危险命令会在执行前要求确认
- 小任务优先使用 `search` 定位相关文件，再读取少量命中文件，减少无关输出
