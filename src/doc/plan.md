# 1.0 实现计划

> 按照 Superpowers 的流程，本计划采用：先文档，后测试，再实现。每个小阶段完成后由开发者手动提交。

## 文件结构

计划创建以下文件：

```text
1.0/
├── README.md
├── doc/
│   ├── 1.0软件开发流程.md
│   ├── requirements.md
│   ├── plan.md
│   └── log.md
├── src/
│   └── nju_agent/
│       ├── __init__.py
│       ├── __main__.py
│       ├── agent.py
│       ├── config.py
│       ├── llm.py
│       └── tools.py
└── tests/
    ├── test_agent.py
    ├── test_config.py
    ├── test_llm.py
    └── test_tools.py
```

## 阶段 1：文档准备

目标：先把 1.0 要做什么写清楚。

文件：

- `1.0/README.md`
- `1.0/doc/1.0软件开发流程.md`
- `1.0/doc/requirements.md`
- `1.0/doc/plan.md`
- `1.0/doc/log.md`

验证：

```bash
find 1.0 -maxdepth 3 -type f | sort
```

建议提交：

```bash
git add 1.0
git commit -m "docs: define 1.0 scope and workflow"
git push
```

## 阶段 2：项目骨架

目标：让 Python 包能被运行。

先写测试：

- `1.0/tests/test_agent.py`

测试目标：

- 可以导入 `nju_agent`。
- `python -m nju_agent` 可以启动。

再实现：

- `1.0/src/nju_agent/__init__.py`
- `1.0/src/nju_agent/__main__.py`

验证：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests/test_agent.py -q
PYTHONPATH=1.0/src python -m nju_agent
```

建议提交：

```bash
git add 1.0
git commit -m "feat: add 1.0 python package skeleton"
git push
```

## 阶段 3：本地工具

目标：实现 agent 能使用的本地工具。

先写测试：

- `1.0/tests/test_tools.py`

测试目标：

- `list_files(root)` 返回目录文件名。
- `read_file(root, path)` 读取文本内容。
- `write_file(root, path, content)` 写入文本内容。
- `run_command(root, command)` 在当前工作区本地执行命令并返回输出。
- 文件路径不能逃出 `root`。
- 命令超时时返回错误。
- 只读会话下不暴露 `write_file` / `run_command`。

再实现：

- `1.0/src/nju_agent/tools.py`

验证：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests/test_tools.py -q
```

建议提交：

```bash
git add 1.0
git commit -m "feat: add local tools"
git push
```

## 阶段 4：模型配置和调用

目标：封装大模型 API 调用，不把 API key 写死。

先写测试：

- `1.0/tests/test_config.py`
- `1.0/tests/test_llm.py`

测试目标：

- 能从环境变量读取 `DEEPSEEK_API_KEY`。
- 能读取可选的 `DEEPSEEK_BASE_URL`。
- 能读取可选的 `DEEPSEEK_MODEL`。
- 没有 API key 时给出清楚错误。

再实现：

- `1.0/src/nju_agent/config.py`
- `1.0/src/nju_agent/llm.py`

验证：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests -q
```

建议提交：

```bash
git add 1.0
git commit -m "feat: add llm configuration"
git push
```

## 阶段 5：Agent 主循环

目标：把用户任务、模型回复、工具调用和工具结果串起来。

先写测试：

- `1.0/tests/test_agent.py`

测试目标：

- 如果模型直接返回最终回答，agent 直接结束。
- 如果模型请求工具，agent 执行工具后继续循环。
- 超过最大轮数时停止。
- 工具失败时把错误返回给模型。
- 只读模式下只暴露 `list_files` / `read_file`，可写模式下再开放 `write_file` / `run_command`；危险命令执行前先确认。

再实现：

- `1.0/src/nju_agent/agent.py`

验证：

```bash
PYTHONPATH=1.0/src pytest 1.0/tests/test_agent.py -q
```

建议提交：

```bash
git add 1.0
git commit -m "feat: add minimal agent loop"
git push
```

## 阶段 6：命令行体验

目标：让用户能从终端运行 agent。

修改：

- `1.0/src/nju_agent/__main__.py`

运行方式：

```bash
PYTHONPATH=1.0/src python -m nju_agent
```

输出内容：

- 用户任务。
- 每次工具调用。
- 工具结果摘要。
- 最终回答。

验证：

```bash
PYTHONPATH=1.0/src python -m nju_agent
```

建议提交：

```bash
git add 1.0
git commit -m "feat: add command line agent"
git push
```

## 阶段 7：整理演示

目标：准备 README 和视频要展示的任务。

修改：

- `README.txt`
- `1.0/README.md`
- `1.0/doc/log.md`

演示任务：

```text
创建一个 hello.py，让它打印 hello nju，然后运行它。
```

验证：

```bash
git status --short
PYTHONPATH=1.0/src pytest 1.0/tests -q
```

建议提交：

```bash
git add README.txt 1.0
git commit -m "docs: prepare 1.0 demo"
git push
```
