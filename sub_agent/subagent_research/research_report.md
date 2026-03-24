# Sub-agent 模式调研报告（检索日期：2026-03-23）

> 目标：调研 DeepSeek、GLM、MiniMax、Kimi、ChatGPT/OpenAI、Claude Code 对“sub-agent / 多智能体 / delegation / handoff / tool orchestration”的官方支持方式，并据此设计一个统一、可扩展、低耦合的 Python 实现。

---

## 1. 结论先行

### 1.1 谁真正提供了“原生 sub-agent”一等公民能力？

**第一梯队（原生概念清晰、官方直接支持）**

1. **Claude Code / Claude Agent SDK**
   - 明确提供 **subagents** 概念。
   - Claude Code 支持把 subagent 定义为 **Markdown + YAML frontmatter** 文件。
   - Claude Agent SDK 支持在 SDK 里定义/调用 subagents，并强调：**上下文隔离、并行、专用指令**。

2. **OpenAI / ChatGPT（开发者侧即 OpenAI Agents SDK）**
   - 官方主概念不是 “subagent”，而是 **specialized agents + handoffs**。
   - 从工程语义上看，这就是“sub-agent delegation”的正式实现。

**第二梯队（没有统一叫 subagent，但有足够强的等价能力）**

3. **MiniMax**
   - 重点在 **Tool Use + Interleaved Thinking + Anthropic/OpenAI 兼容格式**。
   - 官方还提供 **Mini-Agent** 作为最佳实践项目。
   - 更偏“agent runtime + tool loop”，不是显式子代理配置系统。

4. **Kimi / Moonshot**
   - 重点在 **Tool Use / 官方工具 / Agent 搭建指南 / ACP / MCP**。
   - 有很强的 agent 能力，但没有像 Claude Code 那样独立命名的 subagent 文件规范。

5. **GLM / 智谱**
   - 重点在 **Function Calling、结构化输出、智能体开发平台、MCP、层次化智能体设计**。
   - 更偏“平台 + MCP + function calling + agentic coding”的组合拳。

6. **DeepSeek**
   - 重点在 **OpenAI-compatible chat/function calling/json output**，以及新版模型把 **thinking 融入 tool-use**。
   - 我本次检索到的官方公开文档中，没有找到类似 Claude Code 的 “subagent 配置页”；更适合把 sub-agent 映射成 **delegation tool**。

---

## 2. 官方文档总表

| 厂商 | 官方能力形态 | 是否原生 sub-agent | 你应该如何适配 |
|---|---|---:|---|
| OpenAI / ChatGPT | Agents SDK + handoffs + Responses API tools | 半原生（handoff 等价） | 用 `SubAgentDefinition -> Agent/Handoff` 序列化 |
| Claude Code | Markdown/YAML subagents + Agent SDK subagents | 是 | 直接生成 `.md` subagent 文件 |
| DeepSeek | OpenAI-compatible chat + tools + json output | 否 | 映射为 function tool + JSON mode |
| GLM | Function calling + JSON + MCP + 智能体平台 | 否（但层次化 agent 官方明确建议） | 映射为 function tool / MCP routing |
| Kimi | Tool Use + 官方工具 + Agent guide + ACP/MCP | 否 | 映射为 function tool / Formula tools / ACP client |
| MiniMax | Tool Use + Interleaved Thinking + OpenAI/Anthropic 兼容 + Mini-Agent | 否（但 agent runtime 很强） | 同时输出 OpenAI 兼容与 Anthropic 兼容两套格式 |

---

## 3. 各家官方资料详细拆解

### 3.1 OpenAI / ChatGPT

**核心官方资料**
- OpenAI Agents SDK: https://developers.openai.com/api/docs/guides/agents-sdk
- Responses API: https://developers.openai.com/api/reference/resources/responses/methods/create
- Agents SDK handoffs: https://openai.github.io/openai-agents-python/handoffs/
- OpenAI multi-agent cookbook: https://developers.openai.com/cookbook/examples/orchestrating_agents

**官方语义**
- 不是把“sub-agent”作为单独产品名，而是把“专业化智能体之间的任务转移”建模成 **handoff**。
- 这非常适合你的需求：主控 agent 负责 triage / route，专业 agent 负责具体子任务。

**工程特点**
- 优势：抽象干净，官方 tracing/handoff 语义强。
- 注意：OpenAI 真正生产级推荐是 **Responses API + Agents SDK**，不要继续围绕老旧 Assistants 思维设计。

**适配建议**
- 把统一 `SubAgentDefinition` 映射成：
  1. `Agent(name, instructions, tools, handoff_description)`
  2. 或者把子代理导出成 Responses API 的 `function tool`，便于跨供应商复用。

---

### 3.2 Claude Code / Claude Agent SDK

**核心官方资料**
- Claude Code subagents: https://code.claude.com/docs/en/sub-agents
- Claude Agent SDK subagents: https://platform.claude.com/docs/en/agent-sdk/subagents
- Claude Agent SDK overview: https://platform.claude.com/docs/en/agent-sdk/overview

**官方语义**
- 这是本次调研里最明确的原生 sub-agent 体系。
- Claude Code subagent 的定义方式极其清楚：**Markdown 文件 + YAML frontmatter**。

**官方配置字段（非常重要）**
- `name`
- `description`
- `tools`
- `disallowedTools`
- `model`
- `mcpServers`

**为什么它强**
- 真正强调：
  - 每个 subagent **自己的上下文窗口**；
  - 自己的 **system prompt**；
  - 自己的 **工具权限**；
  - 可通过 `Agent(worker, researcher)` 限制可再委派的代理类型。

**适配建议**
- Claude Code 适配层应输出 `.md` 文件，而不是仅仅输出 JSON。
- 这是跨供应商框架里唯一一个“文件即配置”的主流目标格式，必须单独处理。

---

### 3.3 DeepSeek

**核心官方资料**
- First API Call / OpenAI-compatible API: https://api-docs.deepseek.com/
- Function Calling: https://api-docs.deepseek.com/guides/function_calling/
- JSON Output: https://api-docs.deepseek.com/guides/json_mode/
- Tool Calls（中文页）: https://api-docs.deepseek.com/zh-cn/guides/tool_calls
- DeepSeek-V3.2 release（Agent/tool-use 说明）: https://api-docs.deepseek.com/news/news251201

**官方语义**
- DeepSeek 的开发者接口本质上是 **OpenAI 兼容聊天接口**。
- 原生文档重点不在“subagent 配置”，而在：
  - `messages`
  - `tools`
  - `response_format={"type": "json_object"}`
  - `deepseek-chat` / `deepseek-reasoner`
- 新版文档说明里，DeepSeek-V3.2 已把 **thinking 直接融入 tool-use**。

**适配建议**
- 最佳方式：把 sub-agent 当成一个 delegation function tool。
- 主控 agent 决定是否调用 `delegate_to_xxx(task, context)`。
- 深度思考场景下，保留 `reasoning_content` / 思维链续传机制时，要单独封装会话逻辑。

---

### 3.4 GLM / 智谱

**核心官方资料**
- GLM-5 模型页: https://docs.bigmodel.cn/cn/guide/models/text/glm-5
- 工具调用: https://docs.bigmodel.cn/cn/guide/capabilities/function-calling
- 结构化输出: https://docs.bigmodel.cn/cn/guide/capabilities/struct-output
- 智能体开发平台: https://docs.bigmodel.cn/cn/guide/platform/intelligent-agent
- MCP & 智能体技巧: https://docs.bigmodel.cn/cn/coding-plan/best-practice/mcp-and-agent
- 联网搜索 MCP: https://docs.bigmodel.cn/cn/coding-plan/mcp/search-mcp-server

**官方语义**
- GLM 没有单页“sub-agent 规范”，但官方已经明确把 agentic engineering、MCP、多步骤工具协同、层次化设计作为核心方向。
- 官方最佳实践页面甚至直接讲 **智能体的层次化设计**。

**适配建议**
- 运行时：用 function calling 做 delegation。
- 扩展层：用 MCP 给不同 sub-agent 绑定特定外部能力。
- 如果未来接入智谱智能体开发平台，可把我们的 `SubAgentDefinition` 继续映射成平台节点/角色配置。

---

### 3.5 Kimi / Moonshot

**核心官方资料**
- 用 Kimi K2.5 搭建 Agent: https://platform.moonshot.cn/docs/guide/use-kimi-k2-to-setup-agent
- 工具调用 / Function Calling: https://platform.moonshot.cn/docs/api/tool-use
- 官方工具集成说明: https://platform.moonshot.cn/docs/guide/use-official-tools
- Kimi CLI / ACP / MCP: https://platform.moonshot.cn/docs/guide/kimi-cli-support
- Playground 配置 ModelScope MCP: https://platform.moonshot.cn/docs/guide/configure-the-modelscope-mcp-server

**官方语义**
- Kimi 强项在于：
  - 通用 tool calling；
  - 官方 Formula 工具；
  - Kimi CLI 可作为 agent server；
  - 原生支持 **ACP**，并支持 **MCP config file**。
- 对“sub-agent”没有像 Claude Code 一样独立文件规范，但生态上更开放。

**适配建议**
- API 层：映射成 `tools[]` 中的 function tool。
- 平台层：可把工具切换为 Kimi 官方 Formula URI，例如：
  - `moonshot/web-search:latest`
  - `moonshot/rethink:latest`
  - `moonshot/code_runner:latest`
- 客户端层：如果做 IDE/CLI 集成，可以额外输出 ACP/MCP 侧配置。

---

### 3.6 MiniMax

**核心官方资料**
- Tool Use & Interleaved Thinking: https://platform.minimax.io/docs/guides/text-m2-function-call
- OpenAI-compatible API: https://platform.minimax.io/docs/api-reference/text-openai-api
- Anthropic-compatible API: https://platform.minimax.io/docs/api-reference/text-anthropic-api
- MCP guide: https://platform.minimax.io/docs/guides/mcp-guide
- Mini-Agent: https://platform.minimax.io/docs/token-plan/mini-agent
- MiniMax M2 agent generalization note: https://platform.minimax.io/docs/guides/text-m2-agent-generalization

**官方语义**
- MiniMax-M2.7 被官方明确定位为 **Agentic Model**，核心卖点是：
  - Tool Use
  - Interleaved Thinking
  - Anthropic / OpenAI 兼容接入
- 官方还给了 **Mini-Agent** 项目，且明确写着“fully compatible with the Anthropic API”。

**适配建议**
- 必须同时支持两种序列化输出：
  1. `OpenAI-compatible`
  2. `Anthropic-compatible`
- 在 M2.7 中，如果采用 interleaved thinking，调用工具时要把 **完整 response / reasoning 字段** 回传到会话历史，而不是只保留文本。

---

## 4. 最新顶会 / 顶刊 / 高质量论文（与 sub-agent 改进直接相关）

下面只列对你的实现最有价值的几篇，不追求凑数量，而是追求对架构有直接指导意义。

### 4.1 HiAgent — ACL 2025 Long
- 论文：HiAgent: Hierarchical Working Memory Management for Solving Long-Horizon Agent Tasks with Large Language Models
- 链接：https://aclanthology.org/2025.acl-long.1575/
- 开源：https://github.com/HiAgent2024/HiAgent

**关键启发**
- 用 **subgoal 作为 memory chunk** 很关键。
- 我们的框架里因此采用了：
  - `active_subgoal`
  - `active_entries`
  - `archived_summaries`
- 这比“所有历史直接拼 prompt”更适合长程 sub-agent 协作。

### 4.2 MultiAgentBench — ACL 2025 Long
- 论文：https://aclanthology.org/2025.acl-long.421/
- 代码：https://github.com/GGeminii/MultiAgentBench

**关键启发**
- 多智能体系统不能只评“最后答对没”，还要评 **协作质量**。
- 对工程实现的启发是：
  - 需要 trace；
  - 需要 delegation decision；
  - 需要结构化中间产物。

### 4.3 MegaAgent — Findings of ACL 2025
- 论文：https://aclanthology.org/2025.findings-acl.259/
- 代码：https://github.com/Xtra-Computing/MegaAgent

**关键启发**
- 动态生成 agent、并行执行、系统监控，是大任务下的核心能力。
- 对应到本实现，就是：
  - router 负责选 agent；
  - orchestrator 负责并行；
  - traces 负责观测；
  - provider adapters 负责跨生态执行。

### 4.4 Reinforce LLM Reasoning through Multi-Agent Reflection — ICML 2025
- 论文：https://proceedings.mlr.press/v267/yuan25l.html

**关键启发**
- 多 agent 的价值不只在“分工”，也在 **反思与 refinement**。
- 这提示我们：
  - coordinator 和 specialist 不应该只有一次 handoff；
  - 实际生产里可加入 `critic/reviewer subagent` 形成二次 refinement 环。

### 4.5 AgentDropout — ACL 2025 Long
- 论文：https://aclanthology.org/2025.acl-long.1170/
- 代码：https://github.com/wangzx1219/AgentDropout

**关键启发**
- 多 agent 并不是越多越好。
- 动态删去低价值 agent，能减少 token 且提升效果。
- 我们因此在路由器里加入 **pruning / min_score / top-k parallel** 思路。

### 4.6 Memory OS of AI Agent — EMNLP 2025 Main
- 论文：https://aclanthology.org/2025.emnlp-main.1318/

**关键启发**
- memory 应该被看成系统层能力，而不是 prompt 小技巧。
- 其“短期 / 中期 / 长期”层级结构对长对话、多 sub-agent 的持续运行非常关键。

### 4.7 Multi-Agent Collaboration via Evolving Orchestration — OpenReview, 2025 接收
- 论文：https://openreview.net/forum?id=L0xZPXT3le

**关键启发**
- orchestration 不应该是静态树，而应该根据任务状态动态进化。
- 这支持我们把“统一抽象 + 动态路由 + provider serializer”作为主线，而不是写死工作流。

### 4.8 OrchestrationBench — ICLR 2026 poster / OpenReview
- 论文：https://openreview.net/forum?id=Oljnxmf4pc
- 代码：https://github.com/kakao/OrchestrationBench

**关键启发**
- function calling 往往比 planning 更稳；planning 才是多 agent 里真正拉开差距的部分。
- 这意味着：
  - 代码实现里要显式区分 **planning** 和 **tool execution**；
  - 不要把路由、工具执行、最终 merge 混成一层。

---

## 5. 高质量开源项目（落地价值最高）

### 5.1 OpenAI Agents SDK
- 仓库：https://github.com/openai/openai-agents-python
- 价值：handoffs / tracing / sessions / guardrails 的抽象非常适合生产系统。

### 5.2 LangGraph
- 仓库：https://github.com/langchain-ai/langgraph
- 价值：最适合做“可控工作流 + 图式编排 + 长运行状态机”。

### 5.3 Microsoft AutoGen
- 仓库：https://github.com/microsoft/autogen
- 价值：多 agent 对话、事件驱动、生态成熟。

### 5.4 CrewAI
- 仓库：https://github.com/crewAIInc/crewAI
- 价值：角色化、流程化、多 agent 任务分发清晰，适合业务团队快速搭建。

### 5.5 smolagents
- 仓库：https://github.com/huggingface/smolagents
- 价值：抽象很薄，适合学习“把 agent 做小、做透”的方式。

### 5.6 OpenHands
- 仓库：https://github.com/OpenHands/OpenHands
- 价值：软件工程代理方向最值得关注的开源项目之一，体现了 agent runtime、工具使用、环境交互、云端扩展的真实复杂度。

---

## 6. 面向你这个需求的创新改进建议

结合上面的官方文档、论文和开源实现，我建议不要直接抄任何一家，而是做一个 **统一语义层 + 多供应商格式层** 的架构。

### 6.1 统一语义层（Canonical Layer）

定义统一的 `SubAgentDefinition`：
- `name`
- `description`
- `system_prompt`
- `instructions`
- `tags`
- `capabilities`
- `tools`
- `model_preferences`
- `constraints`

**价值**：
- 业务逻辑与供应商格式解耦。
- 你能先写“sub-agent 的真实能力”，再决定如何落地到某一家平台。

### 6.2 层次化记忆（Hierarchical Memory）

融合 HiAgent + MemoryOS：
- 当前子目标的活跃上下文：`active_entries`
- 历史压缩摘要：`archived_summaries`
- 每个 subgoal 拥有自己的 memory bucket

**价值**：
- 限制上下文膨胀。
- 更适合长程任务和并行代理。

### 6.3 动态路由 + 剪枝（Routing + Dropout）

融合 MegaAgent + AgentDropout：
- 不广播给所有 agent；
- 基于 capability overlap 打分；
- 只挑 top-k；
- 低分直接剪掉。

**价值**：
- 降 token；
- 降系统复杂度；
- 更适合线上运行。

### 6.4 Planning / Execution / Merge 三段式

融合 OrchestrationBench：
1. `route`：先判断该让谁做；
2. `execute`：再去跑 sub-agent；
3. `merge`：最后汇总结果。

**价值**：
- 更便于 debug；
- 更容易做评测；
- 更利于 trace 与 observability。

### 6.5 Provider Serializer 层

针对 6 家分别输出：
- OpenAI/ChatGPT：Agents SDK/Handoff 风格 + Responses 工具风格
- Claude Code：Markdown + YAML frontmatter
- DeepSeek：OpenAI-compatible `tools[]`
- GLM：Function calling + JSON mode
- Kimi：Function tool + Formula refs + ACP/MCP 说明
- MiniMax：OpenAI-compatible 与 Anthropic-compatible 双输出

**价值**：
- 真正做到一次定义，多端落地。

---

## 7. 本次代码实现与报告的对应关系

本次交付代码已经实现了下面这些点：

1. **抽象类 / 基类**
   - `AbstractSubAgent`
   - `AbstractProviderAdapter`
   - `AbstractRouter`
   - `AbstractMemory`

2. **核心数据模型**
   - `SubAgentDefinition`
   - `TaskEnvelope`
   - `TaskResult`
   - `DelegationDecision`
   - `ProviderArtifact`

3. **层次化记忆**
   - `HierarchicalWorkingMemory`

4. **路由器**
   - `KeywordCapabilityRouter`

5. **主控编排器**
   - `SubAgentOrchestrator`

6. **供应商格式适配器**
   - `OpenAIChatGPTAdapter`
   - `ClaudeCodeAdapter`
   - `DeepSeekAdapter`
   - `GLMAdapter`
   - `KimiAdapter`
   - `MiniMaxAdapter`

7. **具体 sub-agent 实现**
   - `ResearchSubAgent`

8. **调用示例**
   - `examples/demo_subagent.py`
   - 运行后自动生成 `examples/provider_artifacts.json`

---

## 8. 你下一步最值得继续做的两件事

### 8.1 增加“reviewer / critic subagent”
- 用于二次校验 research / coding 输出。
- 这是把 ICML 2025 的 multi-agent reflection 真正落地到工程里。

### 8.2 把 provider adapter 从“序列化”升级为“可执行 client”
- 目前代码重点是 **格式正确、结构清晰、可扩展**。
- 下一步可以：
  - 接入真实 API key；
  - 为 OpenAI / DeepSeek / GLM / Kimi / MiniMax 增加执行 client；
  - 为 Claude Code 生成真实 subagent 文件并自动落盘。

---

## 9. 我对这 6 家的最终判断

### 最适合“原生 sub-agent 工程”的：Claude Code
因为它真的把 subagent 做成了正式的配置对象和运行时实体。

### 最适合“多专业 agent 编排”的：OpenAI Agents SDK
因为 handoff 语义最清晰、追踪和框架化最好。

### 最适合“兼容层 / 中间层接入”的：DeepSeek、Kimi、GLM
因为它们都可以很好地通过 OpenAI-style tools/function calling 被统一适配。

### 最适合“复杂推理 + tool loop”的：MiniMax M2.7
因为 interleaved thinking + Anthropic/OpenAI 双兼容，对 agent runtime 非常友好。

---

## 10. 附录：官方链接清单

### OpenAI / ChatGPT
- https://developers.openai.com/api/docs/guides/agents-sdk
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://openai.github.io/openai-agents-python/handoffs/
- https://developers.openai.com/cookbook/examples/orchestrating_agents

### Claude Code / Anthropic
- https://code.claude.com/docs/en/sub-agents
- https://platform.claude.com/docs/en/agent-sdk/subagents
- https://platform.claude.com/docs/en/agent-sdk/overview

### DeepSeek
- https://api-docs.deepseek.com/
- https://api-docs.deepseek.com/guides/function_calling/
- https://api-docs.deepseek.com/guides/json_mode/
- https://api-docs.deepseek.com/news/news251201

### GLM / 智谱
- https://docs.bigmodel.cn/cn/guide/models/text/glm-5
- https://docs.bigmodel.cn/cn/guide/capabilities/function-calling
- https://docs.bigmodel.cn/cn/guide/capabilities/struct-output
- https://docs.bigmodel.cn/cn/guide/platform/intelligent-agent
- https://docs.bigmodel.cn/cn/coding-plan/best-practice/mcp-and-agent

### Kimi / Moonshot
- https://platform.moonshot.cn/docs/guide/use-kimi-k2-to-setup-agent
- https://platform.moonshot.cn/docs/api/tool-use
- https://platform.moonshot.cn/docs/guide/use-official-tools
- https://platform.moonshot.cn/docs/guide/kimi-cli-support

### MiniMax
- https://platform.minimax.io/docs/guides/text-m2-function-call
- https://platform.minimax.io/docs/api-reference/text-openai-api
- https://platform.minimax.io/docs/api-reference/text-anthropic-api
- https://platform.minimax.io/docs/token-plan/mini-agent
- https://platform.minimax.io/docs/guides/mcp-guide
