# 1.0 开发日志

## 2026-08-27

### 文档阶段

目标：

- 先明确 1.0 的范围。
- 先记录开发流程，再开始写代码。
- 让仓库历史能够体现开发过程。

已完成：

- 创建 `1.0/README.md`。
- 创建 `1.0/doc/1.0软件开发流程.md`。
- 创建 `1.0/doc/requirements.md`。
- 创建 `1.0/doc/plan.md`。
- 创建 `1.0/doc/log.md`。

下一步：

- 由开发者提交文档阶段。
- 提交后开始阶段 2：项目骨架。

### 阶段 2：项目骨架

目标：

- 让 `nju_agent` 可以被 Python 导入。
- 让 `python -m nju_agent` 可以从命令行启动并进入对话模式。

先失败的测试：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests/test_agent.py -q
```

失败原因：

```text
ModuleNotFoundError: No module named 'nju_agent'
```

修改内容：

- 创建 `1.0/tests/test_agent.py`。
- 创建 `1.0/src/nju_agent/__init__.py`。
- 创建 `1.0/src/nju_agent/__main__.py`。

验证命令：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests/test_agent.py -q
PYTHONPATH=1.0/src python -m nju_agent
```

验证结果：

```text
2 passed
进入对话模式，输入 /exit 退出
```

下一步：

- 阶段 3：实现本地工具。

### 阶段 3：本地工具

目标：

- 实现 agent 后续会调用的本地能力：列目录、读文件、写文件、执行命令。
- 给文件路径加工作目录边界。
- 给命令执行加超时限制。

先失败的测试：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests/test_tools.py -q
```

失败原因：

```text
ModuleNotFoundError: No module named 'nju_agent.tools'
```

修改内容：

- 创建 `1.0/tests/test_tools.py`。
- 创建 `1.0/src/nju_agent/tools.py`。
- 实现 `list_files`、`read_file`、`write_file`、`run_command`。

验证命令：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests/test_tools.py -q
PYTHONPATH=1.0/src pytest 1.0/tests -q
```

验证结果：

```text
5 passed
7 passed
```

下一步：

- 阶段 4：实现模型配置和调用封装。

### 阶段 4：模型配置和调用

目标：

- 从环境变量读取模型配置。
- 通过 DeepSeek 兼容客户端调用 Responses API。
- 把模型的工具请求接回本地工具执行。

修改内容：

- 创建 `1.0/src/nju_agent/config.py`。
- 创建 `1.0/src/nju_agent/llm.py`。
- 创建 `1.0/src/nju_agent/agent.py`。
- 更新 `1.0/src/nju_agent/__main__.py`。
- 新增 `1.0/tests/test_config.py`。
- 新增 `1.0/tests/test_llm.py`。
- 扩展 `1.0/tests/test_agent.py`。

验证命令：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests -q
python -m compileall 1.0/src/nju_agent
```

验证结果：

```text
10 passed
```

下一步：

- 整理 README 和提交说明。

### 口径统一

目标：

- 让仓库说明统一描述为“模型客户端 + 本地工具 + 自写 agent 循环”。

已完成：

- 更新 `README.txt`。
- 更新 `1.0/README.md`。
- 更新 `1.0/doc/1.0软件开发流程.md`。
- 更新 `1.0/doc/requirements.md`。

### DeepSeek 切换

目标：

- 将默认模型接入切换为 DeepSeek。
- 让 agent 在本地保存完整上下文，适配 DeepSeek Responses API 的无状态调用方式。

已完成：

- 更新 `1.0/src/nju_agent/config.py`。
- 更新 `1.0/src/nju_agent/llm.py`。
- 更新 `1.0/src/nju_agent/agent.py`。
- 更新测试文件。

### 会话级权限控制

目标：

- 默认只读。
- 只有切到可写时，才允许写文件和执行命令。
- 让权限和会话绑定，避免影响其他会话。

已完成：

- 为会话增加 `access_mode`。
- 新增 `/access` 切换权限。
- 只读时只暴露 `list_files` / `read_file`。
- 只读时对 `write_file` / `run_command` 做执行期拦截。
- 更新相关测试。

## 2026-08-29

### 轻量 subagent 分工

目标：

- 在不引入 agent 框架、不增加多个执行者的前提下，加入可选 planner / reviewer 分工。
- planner 只负责规划，reviewer 只负责审查，executor 仍沿用现有工具调用循环。

已完成：

- 新增 planner / reviewer prompt。
- 新增 `/subagents` 命令，用于打开或关闭分工模式。
- planner / reviewer 调用不暴露任何本地工具。
- reviewer 可要求 executor 最多再执行一轮修正。
- 为 `run_agent` 和交互式会话补充相关测试。

验证命令：

```bash
PYTHONPATH=src/src pytest src/tests -q
```

验证结果：

```text
25 passed
```

## 2026-09-01

### 搜索工具优化

目标：

- 减少小任务中无关文件读取和过多输出。
- 让 agent 先通过关键词定位相关文件，再读取少量命中文件。

已完成：

- 新增 `search_files` 本地搜索工具。
- 在 tool calling 工具列表中新增 `search`。
- 只读模式下开放 `search` / `list_files` / `read_file`。
- 更新 system prompt，提示小任务优先搜索定位再精读。
- 补充搜索工具和工具注册相关测试。

验证命令：

```bash
PYTHONPATH=src/src pytest src/tests -q
```

验证结果：

```text
43 passed
```
