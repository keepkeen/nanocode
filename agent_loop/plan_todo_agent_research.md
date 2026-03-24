# Plan / Todo / Agent Loop 调研报告（2026-03-23）

## 1. 研究范围

对象：

- DeepSeek
- GLM（智谱）
- MiniMax
- Kimi / Moonshot
- ChatGPT / OpenAI
- Claude Code / Anthropic

聚焦点：

1. 官方是否存在明确的 **Plan / 规划模式**
2. 官方是否存在明确的 **Todo / 任务列表 / 进度追踪模式**
3. 官方是否提供 **思考 + 工具调用 + 多轮回传** 的 agent loop 文档
4. 是否有可直接借鉴的 **runtime / SDK / config / subagent / skill** 形式

---

## 2. 总结结论

### 2.1 最明确支持“Plan + Todo”双机制的官方体系

**Claude Code / Anthropic** 最完整：

- 明确有 **Plan Mode**
- 明确暴露 **TodoWrite** 工具
- Claude Code SDK 官方还有 **todo-tracking** 文档
- 同时支持 **subagents**、**MCP**、**hooks**、**settings.json**、**output styles**

这意味着 Claude Code 不只是“会规划”，而是把“规划”“任务追踪”“子代理”“工具运行时”都产品化了。

### 2.2 最强的“思考 + 工具调用 + 回传 reasoning”官方 API 组合

从 API 设计上看，以下几家都把“工具调用间继续思考”文档化了：

- **Anthropic**：extended thinking + interleaved thinking
- **DeepSeek**：thinking mode + tool calls，且必须回传 `reasoning_content`
- **GLM**：交错式思考 + 工具调用，必须保留 reasoning content
- **MiniMax**：tool use + interleaved thinking
- **Kimi**：2025 下半年开始明显强化 Agentic Coding / tool call / Claude Code 兼容

### 2.3 OpenAI / ChatGPT 的特点

OpenAI / ChatGPT 官方更像是把能力拆在三层：

- **API 层**：Responses API / reasoning / tools / Agents SDK
- **产品层**：ChatGPT Tasks / Projects / Codex cloud
- **代码代理层**：Codex 的 ask/code 等工作模式

它有完整的 agent building blocks，但不像 Claude Code 那样把 “TodoWrite” 作为一个显式的终端代理工具对外强调。

### 2.4 其余几家关于 “Todo 模式” 的真实情况

除了 Anthropic/Claude Code 之外，我没有搜到其他几家在官方文档里明确把“Todo 模式”作为独立一等能力公开定义。更常见的是：

- 用 **thinking / reasoning** 表达深度规划
- 用 **tool use / function calling** 表达行动能力
- 用 **agent / coding plan / project / tasks / session note** 表达长任务管理

因此，工程上最合理的统一抽象不是“硬把每家都当成原生 Todo 系统”，而是：

- 内部统一维护 `PlanGraph + TodoFrontier`
- 外部适配到不同供应商的 thinking / tool / project / task / subagent 格式

---

## 3. 官方文档矩阵

## 3.1 DeepSeek

### 官方材料

1. Thinking Mode
   - https://api-docs.deepseek.com/guides/thinking_mode
2. Tool Calls
   - https://api-docs.deepseek.com/guides/tool_calls
3. Function Calling / strict mode
   - https://api-docs.deepseek.com/guides/function_calling/
4. Anthropic API compatibility
   - https://api-docs.deepseek.com/guides/anthropic_api
5. DeepSeek-V3.1 release（强调 agent 能力）
   - https://api-docs.deepseek.com/news/news250821

### 结论

- **Plan**：有，体现在 thinking mode 和多轮 tool-call reasoning loop
- **Todo**：未找到独立官方 Todo 模式
- **Agent loop**：有，而且要求显式回传 `reasoning_content`
- **适配价值**：很适合接入统一内部 planner，外部用 OpenAI-chat 风格或 Anthropic-compat 风格发送

### 工程提示

- 若 thinking + tools 联用，必须正确回传 reasoning 内容，否则官方文档明确提到可能报错
- DeepSeek 还提供 Anthropic API 兼容层，因此也能作为 Claude Code 背后的模型源

---

## 3.2 GLM（智谱）

### 官方材料

1. GLM-5
   - https://docs.bigmodel.cn/cn/guide/models/text/glm-5
2. 思考模式
   - https://docs.bigmodel.cn/cn/guide/capabilities/thinking-mode
3. GLM-4.7
   - https://docs.bigmodel.cn/cn/guide/models/text/glm-4.7
4. GLM-4.5（强调 Agent 与思考模式）
   - https://docs.bigmodel.cn/cn/guide/models/text/glm-4.5
5. Claude Code / Coding Plan 集成
   - https://docs.bigmodel.cn/cn/guide/develop/claude
   - https://docs.bigmodel.cn/cn/coding-plan/tool/claude
6. MCP server 文档
   - https://docs.bigmodel.cn/cn/coding-plan/mcp/vision-mcp-server
   - https://docs.bigmodel.cn/cn/coding-plan/mcp/zread-mcp-server

### 结论

- **Plan**：有，官方直接强调长程任务规划与 Agentic Engineering
- **Todo**：未找到独立 Todo 模式
- **Agent loop**：有，且官方写明支持 **交错式思考** 和工具调用
- **适配价值**：非常高，适合作为“长程规划 + 工具执行”的 OpenAI-chat 风格后端

### 工程提示

- GLM 文档对“交错式思考 + 工具”写得很清楚，和 DeepSeek / Anthropic 的模式接近
- GLM 官方还提供 Claude Code / MCP 生态接入文档，说明其工程落点已不仅是 API，而是 coding-agent runtime

---

## 3.3 MiniMax

### 官方材料

1. Tool Use & Interleaved Thinking
   - https://platform.minimax.io/docs/api-reference/text-m2-function-call-refer
2. Mini-Agent（官方开源示例）
   - https://platform.minimax.io/docs/coding-plan/mini-agent
   - https://platform.minimax.io/docs/solutions/mini-agent
3. M2.5 for AI Coding Tools
   - https://platform.minimax.io/docs/guides/text-ai-coding-tools
4. Claude Code 集成
   - https://platform.minimax.io/docs/coding-plan/claude-code
5. SDK 快速开始（Anthropic SDK）
   - https://platform.minimax.io/docs/guides/quickstart-sdk
6. API Overview / Text Generation
   - https://platform.minimax.io/docs/api-reference/api-overview
   - https://platform.minimax.io/docs/api-reference/text-intro

### 结论

- **Plan**：有，尤其体现在 agent execution loop / interleaved thinking / Mini-Agent 文档
- **Todo**：没有官方独立 Todo 模式
- **Agent loop**：很强，Mini-Agent 直接给出完整执行闭环
- **适配价值**：极高，尤其适合参考其官方 Mini-Agent 的抽象方式

### 工程提示

- MiniMax 官方最有价值的不是单页 API，而是 **Mini-Agent** 这个参考实现：
  - execution loop
  - session note memory
  - context summarization
  - skills integration
  - MCP integration
- 这和你要做的“agent 组件化实现”非常接近

---

## 3.4 Kimi / Moonshot

### 官方材料

1. Kimi Code CLI 开始使用
   - https://www.kimi.com/code/docs/en/kimi-cli/guides/getting-started.html
2. 在第三方 Coding Agent 中使用
   - https://www.kimi.com/code/docs/en/more/third-party-agents.html
3. Kimi 长思考模型 API 正式发布
   - https://platform.moonshot.cn/blog/posts/kimi-thinking
4. Kimi Playground 工具调用
   - https://platform.moonshot.cn/blog/posts/kimi-playground
5. Kimi K2 模型更新
   - https://platform.moonshot.cn/blog/posts/kimi-k2-0905
6. Kimi K2 Thinking 模型发布
   - https://platform.moonshot.cn/blog/posts/k2-think
7. 功能更新日志
   - https://platform.moonshot.cn/blog/posts/changelog

### 结论

- **Plan**：有，Kimi Code CLI 文档明确写到会“自主规划并调整行动”
- **Todo**：未找到独立官方 Todo 模式
- **Agent loop**：有，尤其在 thinking preview / K2 tool use / Claude Code 兼容方向上明显增强
- **适配价值**：中高，Kimi 的强项是 coding-agent 和 OpenAI / Anthropic 兼容生态接入

### 工程提示

- `kimi-thinking-preview` 暴露 `reasoning_content`，但早期文档明确说不支持 tool calls
- 2025 年下半年 K2 系列开始强化 tool call、Claude Code 兼容、context caching、agentic coding
- 这意味着 Kimi 的 API 能力在时间上演进较快，适配层应避免把老模型和新模型混在一个固定假设里

---

## 3.5 ChatGPT / OpenAI

### 官方材料

1. Reasoning models
   - https://platform.openai.com/docs/guides/reasoning
2. Reasoning best practices
   - https://platform.openai.com/docs/guides/reasoning-best-practices
3. Responses API reference
   - https://platform.openai.com/docs/api-reference/responses/create
4. Tools / Function calling
   - https://platform.openai.com/docs/guides/tools
   - https://platform.openai.com/docs/guides/function-calling
5. Agents SDK
   - https://platform.openai.com/docs/guides/agents-sdk/
6. Codex cloud / code generation
   - https://platform.openai.com/docs/codex
   - https://platform.openai.com/docs/guides/code-generation
7. ChatGPT Tasks
   - https://help.openai.com/en/articles/10291617-tasks-in-chatgpt
8. ChatGPT Projects
   - https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt

### 结论

- **Plan**：有，reasoning models 明确面向 multi-step planning / agentic workflows
- **Todo**：产品层有 **Tasks in ChatGPT**，但 API 层没有 Claude Code 那样的显式 TodoWrite 工具
- **Agent loop**：有，Responses API + tools + Agents SDK 很完整
- **适配价值**：极高，是最适合做“统一内部 canonical schema”的参考实现之一

### 工程提示

- OpenAI 的强项是把“模型 + tools + MCP + SDK + tracing”做成标准 building blocks
- 产品层的 ChatGPT Tasks / Projects 更像“用户工作流管理”；API 层的 Responses / Agents SDK 更适合你要做的 agent 内核

---

## 3.6 Claude Code / Anthropic

### 官方材料

1. Claude Code overview
   - https://docs.anthropic.com/en/docs/claude-code/overview
2. Common workflows / Plan Mode
   - https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/common-workflows
3. Interactive mode（Shift+Tab 切 Plan Mode）
   - https://docs.anthropic.com/en/docs/claude-code/interactive-mode
4. Settings（含 TodoWrite / Task / Subagents 等工具）
   - https://docs.anthropic.com/en/docs/claude-code/settings
5. Model config（含 `opusplan`）
   - https://docs.anthropic.com/en/docs/claude-code/model-config
6. Subagents
   - https://docs.anthropic.com/en/docs/claude-code/sub-agents
7. MCP
   - https://docs.anthropic.com/en/docs/claude-code/mcp
8. Hooks
   - https://docs.anthropic.com/en/docs/claude-code/hooks
9. Extended thinking
   - https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
10. Claude Code SDK 概览
   - https://docs.anthropic.com/en/docs/claude-code/sdk
11. Claude Code SDK Todo tracking（官方多语言文档存在）
   - https://docs.anthropic.com/id/docs/claude-code/sdk/todo-tracking

### 结论

- **Plan**：有，而且是非常明确的 **Plan Mode**
- **Todo**：有，显式工具 **TodoWrite**，并且 SDK 还有 todo tracking 文档
- **Agent loop**：有，extended thinking + interleaved thinking + tools + subagents + MCP
- **适配价值**：最高，尤其适合做你的“外部格式适配模板”参考源

### 工程提示

- Claude Code 的 Plan Mode 非常适合“先规划、后执行”的双阶段代理
- `opusplan` 是一个很重要的信号：Anthropic 官方已经把“规划阶段模型”和“执行阶段模型”区分成推荐工作流
- TodoWrite 的存在说明“进度可视化 / 用户同步”是 Claude Code 产品设计的一等公民

---

## 4. 最新论文与 benchmark（以 2025-2026 为主）

> 说明：2026 的很多结果来自 OpenReview poster / submission 页面，前沿但部分尚未形成最终 archival 版本；我将其与 2025 已公开页面一起分开参考。

### 4.1 值得直接吸收的方法

1. **ToolTree: Efficient LLM Tool Planning via Dual-Feedback Monte Carlo Tree Search and Bidirectional Pruning**
   - ICLR 2026 Poster
   - https://openreview.net/forum?id=Ef5O9gNNLE
   - 启发：不要只做贪心 tool selection；应有 **计划评估器 / critic** 和 **剪枝**

2. **OrchestrationBench: LLM-Driven Agentic Planning and Tool Use in Multi-Domain Scenarios**
   - ICLR 2026 Poster
   - https://openreview.net/forum?id=Oljnxmf4pc
   - 启发：Plan 不只是步骤列表，还要建模 **workflow constraints**

3. **Plancraft: an evaluation dataset for planning with LLM agents**
   - COLM 2025
   - https://openreview.net/forum?id=nSV8Depcpx
   - 启发：需要评估“任务不可解”的场景，不要强行完成

4. **Robotouille: An Asynchronous Planning Benchmark for LLM Agents**
   - ICLR 2025 Poster
   - https://openreview.net/forum?id=OhUoTMxFIH
   - 启发：真实任务常常不是线性顺序，而是异步 / 并行 / 等待型依赖

5. **Planner-R1: Reward Shaping Enables Efficient Agentic RL with Smaller LLMs**
   - ICLR 2026 submission page
   - https://openreview.net/forum?id=CmOaD42eAT
   - 启发：规划器与执行器可以分层，小模型也可承担局部规划 / critic 角色

6. **EvoPlan: Agent-driven Evolutionary Planning for LLM Reasoning**
   - ICLR 2026 submission page
   - https://openreview.net/forum?id=4xPYLcR0I0
   - 启发：可以把 plan 视为可被评估与进化的对象，而不是一次性草稿

### 4.2 对实现最有价值的论文级启发

建议吸收三点：

- **双层结构**：全局 PlanGraph + 局部 TodoFrontier
- **critic 反馈**：计划生成后先校验依赖 / 工具 / 交付物 / 风险
- **可重规划**：遇到工具结果 / blocker 后只重规划局部 frontier，而不是重写整张计划

---

## 5. 高质量开源项目（偏工程价值）

1. **OpenAI Agents SDK**
   - https://github.com/openai/openai-agents-python
   - https://github.com/openai/openai-agents-js
   - 价值：agent / handoff / guardrail / tracing 的清晰抽象

2. **Claude Code**
   - https://github.com/anthropics/claude-code
   - 价值：Plan Mode、subagents、plugin、runtime 设计值得直接借鉴

3. **Mini-Agent（MiniMax 官方）**
   - https://github.com/MiniMax-AI/Mini-Agent
   - 价值：execution loop、session note、skills、MCP 的组合非常贴近目标架构

4. **OpenHands**
   - https://github.com/All-Hands-AI/OpenHands
   - 价值：完整开源 coding-agent 平台，适合看 runtime、CLI、cloud、skill 组织

5. **SWE-agent / mini-SWE-agent**
   - https://github.com/SWE-agent/SWE-agent
   - 价值：真实软件工程任务闭环、评测与 agent 行为设计

6. **Model Context Protocol (MCP) + reference servers**
   - https://github.com/modelcontextprotocol
   - https://github.com/modelcontextprotocol/servers
   - 价值：工具与外部系统连接层的事实标准之一

---

## 6. 最终工程建议

## 6.1 不要把 Plan 和 Todo 混成一个结构

建议拆成两层：

- **PlanGraph**：带依赖和 success criteria 的长期结构
- **TodoFrontier**：当前 3-5 个活跃任务的用户可见进度层

## 6.2 不要把厂商能力写死在核心逻辑中

核心逻辑应只认识：

- messages
- plan
- todo
- tools
- observations
- provider capabilities

然后由 provider adapter 去做：

- OpenAI Responses payload
- OpenAI-chat 风格 payload
- Anthropic Messages payload
- Claude Code settings/subagent/CLAUDE.md 渲染

## 6.3 要把“局部重规划”当成一等能力

最常见失败点不是“第一次不会规划”，而是：

- 工具结果回来后计划失效
- blocker 出现后仍按原路径死走
- 已完成步骤没有正确投影到 todo

所以 agent loop 最重要的不是一次性写大计划，而是：

- critic review
- frontier projection
- observation ingestion
- local replan

## 6.4 Skill 要与 Provider 解耦

Skill 应只负责：

- 提供 domain context
- 提供 tool schema
- 提供 bootstrap plan
- 提供 success definition

Skill 不应直接知道自己跑在 OpenAI、DeepSeek 还是 Claude Code 上。

---

## 7. 本次代码实现选择

本次实现采用：

- `BaseProviderAdapter`
- `BaseSkill`
- `BasePlanCritic`
- `BaseTodoProjector`
- `DualLayerPlanTodoAgent`

并提供：

- OpenAI Responses 适配
- DeepSeek / GLM / Kimi 的 OpenAI-chat 风格适配
- Anthropic / MiniMax 的 Messages 风格适配
- Claude Code 的 settings / subagent / CLAUDE.md 渲染
- ChatGPT 风格的 project / task / progress stub 渲染
- 一个具体 skill：`RepositoryRefactorSkill`

