NJU 推免考核项目：构建编程智能体

当前状态：已实现最小可运行版本，采用本地自写 agent 循环 + DeepSeek 原生 tool calling + 本地工具执行，并支持会话级只读 / 可写权限切换。
新增可选轻量 subagent 分工：planner 只规划、reviewer 只审查，executor 仍是唯一能使用工具的执行者。

实现口径：
1. 只使用模型厂商 API 客户端库
2. 不使用 LangChain、LlamaIndex、AutoGen、CrewAI、OpenAI Agents SDK 等 agent 框架
3. 不依赖服务端托管的代码执行或文件工具
4. 工具执行、上下文管理、循环终止和错误处理都在本地完成
5. 会话默认只读，需要时可用 `/access` 切换到可写
6. 只读模式只暴露 `list_files` / `read_file`，可写模式才开放 `write_file` / `run_command`
7. 可用 `/subagents` 打开或关闭 planner/reviewer 分工模式
8. `run_command` 默认在 Docker 常驻沙箱容器中执行；本地直跑仅作为显式开发模式
