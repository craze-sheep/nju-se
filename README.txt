NJU 推免考核项目：构建编程智能体

当前状态：已实现最小可运行版本，采用本地自写 agent 循环 + DeepSeek 原生 tool calling + 本地工具执行。

实现口径：
1. 只使用模型厂商 API 客户端库
2. 不使用 LangChain、LlamaIndex、AutoGen、CrewAI、OpenAI Agents SDK 等 agent 框架
3. 不依赖服务端托管的代码执行或文件工具
4. 工具执行、上下文管理、循环终止和错误处理都在本地完成
