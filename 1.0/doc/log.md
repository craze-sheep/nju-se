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
- 让 `python -m nju_agent "hello"` 可以从命令行启动。

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
PYTHONPATH=1.0/src python -m nju_agent "hello"
```

验证结果：

```text
2 passed
用户任务：hello
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
