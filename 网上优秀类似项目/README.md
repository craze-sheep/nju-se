# 网上优秀类似项目

这是一份给当前 `coding agent` 项目的参考清单，挑的是更接近“终端里跑、会调工具、会改代码”的项目。

## 优先看这几个

| 项目 | 类型 | 为什么值得看 | 链接 |
| --- | --- | --- | --- |
| Aider | 终端 AI 编程助手 | 很贴近“在本地仓库里对话 + 改文件 + 用 git 协作”的思路 | https://github.com/Aider-AI/aider |
| OpenCode | 终端代码代理 | 交互式终端体验很强，适合看 prompt、工具流和权限控制 | https://github.com/opencode-ai/opencode |
| SWE-agent | 代码修复代理 | 很适合参考“任务 -> 工具 -> 反馈 -> 继续”的 agent 回路 | https://github.com/swe-agent/swe-agent |
| mini-swe-agent | 极简代理 | 代码量很小，适合看最小可行闭环怎么搭 | https://github.com/swe-agent/mini-swe-agent |
| OpenHands | 开源编码代理平台 | 更完整，适合看更大一点的 agent 架构和沙箱设计 | https://github.com/OpenHands/OpenHands |

## 我建议的阅读顺序

1. `Aider`
2. `OpenCode`
3. `mini-swe-agent`
4. `SWE-agent`
5. `OpenHands`

## 适合借鉴的点

- `Aider`：命令行交互、git 感知、补丁式改动。
- `OpenCode`：终端产品感、工具调用流、权限与确认。
- `mini-swe-agent`：最小循环、最少抽象。
- `SWE-agent`：任务拆解、迭代执行、失败后再试。
- `OpenHands`：更完整的 agent 工程组织方式。

## 说明

这里没有直接复制这些项目源码，只是整理成了你后续可以继续看的入口。
