# Agent Memory Package

一个面向 Agent 的统一记忆管理与缓存优化实现，目标是同时解决两件事：

1. **最大程度命中缓存**：把稳定前缀、稳定工具清单、长期记忆固定在前部，把动态用户输入和工具输出推到尾部。
2. **最大程度保留记忆**：把原始消息压缩成分层记忆（Pinned / Semantic / Episodic / Compacted），并以 delta compaction 的方式减少历史膨胀。

## 核心设计

### SPLIT Memory Architecture

- **S**table Prefix Layer：系统指令、工具定义、固定约束、少量 pinned memory 放到开头。
- **P**ersistent Tiered Memory：长期记忆分层管理，区分 instruction / pinned / semantic / episodic / working。
- **L**ossy Delta Compaction：只压缩旧的动态历史，不重写稳定前缀，减少 cache busting。
- **I**solated Dynamic Tail：最新用户输入、最近多轮、动态工具结果只放在尾部。
- **T**enant-safe Namespace：缓存键和记忆命名空间分离，便于多租户隔离。

## 目录结构

- `agent_memory/models.py`：类型定义、数据模型。
- `agent_memory/base.py`：抽象类。
- `agent_memory/memory_store.py`：内存存储实现。
- `agent_memory/compression.py`：规则式 delta compressor。
- `agent_memory/cache.py`：前缀稳定缓存规划器。
- `agent_memory/manager.py`：统一记忆管理器。
- `agent_memory/providers/`：各厂商 payload 适配器。
- `agent_memory/claude_code_memory.py`：导出 `CLAUDE.md` / `MEMORY.md`。
- `examples/`：示例。

## 适配的 Provider

- OpenAI Responses / Chat Completions

- DeepSeek

- GLM / 智谱

- MiniMax（native 与 Anthropic-compatible）

- Kimi / Moonshot

- Anthropic Messages API

- Claude Code 项目记忆文件格式

  

## 调研结果：

### 1) 官方调研结果

**DeepSeek**
 官方把 `/chat/completions` 明确写成**无状态**：服务端不保存上下文，开发者每轮都要把历史 `messages` 自己拼回去。缓存方面，DeepSeek 的“上下文硬盘缓存”默认开启，只对**重复前缀**生效，返回里有 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens`，缓存以 **64 tokens** 为单位、属于“尽力而为”，空闲后会自动清理。对你做 agent 的意义是：DeepSeek 很适合“稳定前缀 + 动态尾部”的编排，但长期记忆必须自己做。

**GLM / 智谱**
 智谱官方“上下文缓存”页把它定义成**隐式自动缓存**：重复或高度相似的系统提示、历史对话、多次重复任务都会命中，命中量体现在 `usage.prompt_tokens_details.cached_tokens`。所以 GLM 的工程策略和 DeepSeek 很像：你不需要显式建 cache，但必须让稳定前缀尽量不抖。

**MiniMax**
 MiniMax 原生文档提供两类能力：一类是 **native automatic caching**，适合 system prompt 复用、固定工具清单和多轮历史；另一类是在 **Anthropic-compatible API** 里显式使用 `cache_control` 断点。它的文本生成文档还给了比普通 chat 更丰富的 role 体系，除了 `system/user/assistant` 之外，还有 `user_system`、`group`、`sample_message_user`、`sample_message_ai` 这类角色。对实现层面，这意味着 MiniMax 需要比 OpenAI 风格更灵活的 role 适配。

**Kimi / Moonshot**
 Moonshot 的多轮对话文档同样把 Kimi chat 写成**无状态**，需要开发者自己维护 `messages`；Kimi API 还明确兼容 OpenAI 格式。另一方面，Moonshot 官方工具列表里已经有 `memory` 工具，说明它把“持久化会话历史和用户偏好”做成了**官方工具能力**。再往缓存侧看，Moonshot 官方博客给了 **Context Caching** 的创建 / 复用流程；而当前定价页又写明 `kimi-k2.5` 支持 **automatic context caching**。所以对 Kimi 最稳妥的理解是：**chat 本身无状态，缓存能力存在且在迭代中，持久记忆可通过官方 memory 工具或你自己的记忆层完成。**

**OpenAI API / ChatGPT**
 这里一定要分开看。**ChatGPT 产品端**有 Saved Memories 和 Reference Chat History，官方明确说它更适合保存**高层偏好**，不适合精确模板或大段逐字文本。**OpenAI API** 则是另一套：Prompt Caching 自动开启，要求**精确前缀匹配**，静态内容应放前面、变量内容放后面；1024 token 以上才会进入缓存路径，`prompt_cache_key` 可以帮助请求路由更稳定，`prompt_cache_retention` 可以控制缓存保留策略。长会话方面，OpenAI 还公开了 **Responses / Conversations / previous_response_id** 的状态管理，以及 **server-side compaction**，通过 `context_management` 自动在上下文接近阈值时产生压缩项。

**Anthropic API / Claude Code**
 Anthropic API 现在公开了两块特别完整：一是 **Prompt caching**，支持 top-level `cache_control` 自动缓存，也支持对单个 content block 做显式断点；官方文档还说明默认 TTL 是 **5 分钟**，可选 **1 小时**，缓存的是 KV 表示和密码学哈希，不存原始文本。二是 **Compaction**：通过 `context_management.edits` 开启，达到阈值后服务端会生成 `compaction` block，后续请求会自动丢弃该 block 之前的历史。

**Claude Code**
 Claude Code 不是普通 API，它是工程工作台。官方文档明确说**每个 session 都从 fresh context 开始**，跨会话知识主要靠两类东西：`CLAUDE.md` 和 auto memory。auto memory 默认开启，按项目存到 `~/.claude/projects/<project>/memory/`，其中 `MEMORY.md` 的**前 200 行**会在每次对话开始时加载；并且官方明确写了：`/compact` 之后，`CLAUDE.md` 会从磁盘重新注入，所以**写进 CLAUDE.md 的规则能跨压缩保留，只存在对话里的临时指令会丢。**

### 2) 横向分析：真正影响 agent 的差异

从 agent 设计角度，这几家其实分成三类。

第一类是 **“无状态会话 + 自动前缀缓存”**：DeepSeek、GLM、MiniMax native 基本都在这个桶里。它们要求你自己维护历史，但会尽量复用稳定前缀。最优策略不是“把所有历史都塞进去”，而是“把**不会变的东西**固定在开头，把**会变的东西**尽量后置”。

第二类是 **“无状态会话 + 显式缓存控制”**：Anthropic、Kimi 的 context caching，以及 MiniMax 的 Anthropic-compatible caching 更接近这一类。这里你不仅要稳定前缀，还要决定**cache breakpoint 放在哪里**、TTL 怎么设、哪些动态 tool result 不该被纳入缓存块。

第三类是 **“缓存 + 会话状态 + 服务端压缩 / 产品记忆”**：OpenAI API、Anthropic API、ChatGPT、Claude Code。它们提供了比“只做前缀缓存”更高一级的原语：conversation state、compaction、saved memory、project memory。真正做 agent 时，应该把这些官方能力当成**底层加速器和兜底层**，而不是把应用级长期记忆 पूरी依赖给 provider。

### 3) 最新顶会 / 顶刊 / 高质量开源：哪些值得吸收

**顶会 / 顶刊里最值得直接吸收到工程里的结论**：

`Don't Break the Cache`（arXiv 2026）直接研究了长流程 agent 里的 prompt caching：在 OpenAI / Anthropic / Google 上，提示缓存能带来 **41–80%** 的 API 成本下降和 **13–31%** 的 TTFT 改善，但“整段 full-context naive 缓存”并不总是最优；把动态内容放到后部、排除动态 tool result，往往更稳。这个结论几乎可以直接变成你的 prompt 编排策略。

在“记忆保留 / 压缩”方向，**ACL 2025** 的 *Pretraining Context Compressor for LLMs with Embedding-Based Memory* 给了“压缩器独立于下游 LLM”的路线，并报告 **4x / 16x** 压缩率下的有效平衡；**EMNLP 2025** 的 *Memory OS of AI Agent* 给出短中长期三级存储和 Storage/Updating/Retrieval/Generation 四模块；**EMNLP 2025** 的 *Coarse-to-Fine Grounded Memory* 则强调 coarse-to-fine 的经验与 tip 检索。你的 agent 记忆层最该吸收的，就是“**分层存储 + 分层召回 + 分阶段压缩**”。

更前沿的 2026 工作里，**ICLR 2026 Oral** 的 *MemAgent* 用分段处理和 overwrite-style memory，把 8K 训练外推到 **3.5M** 级 QA；**ICLR 2026 Poster** 的 *MemoryAgentBench* 则把 memory agent 评估拆成四项：准确检索、test-time learning、长程理解、选择性遗忘。这个评估框架对你后面做 benchmark 很有价值。

系统和推理效率这一侧，**KVCache-Centric Memory for LLM Agents (MemArt)** 直接把记忆表示做进 KV cache，报告 LoCoMo 上准确率提升且 prefill token 下降 **91–135x**；**TACL** 的 TALE 则是更底层的 KV cache 压缩思路，主打 token-adaptive low-rank approximation。对你现在的工程实现，这两篇更适合作为“第二阶段升级方向”，不适合第一版就硬接，因为它们会把系统复杂度一下拉高。

**高质量开源项目里，最值得参考的不是“哪个最强”，而是“哪个解决哪一层问题”**：

做**长期记忆层**，可以看 **Mem0**（自改进 memory layer）、**Letta**（stateful agents / Letta Code）、**LangMem**（从对话抽取记忆和 prompt refinement）、**MemoryOS**（层级化 memory OS）、**Zep / Graphiti**（时间感知知识图谱、可做持续更新和 namespacing）。这些项目共同证明，生产级 agent 记忆层通常不会只靠“保存原始 chat history”，而会把记忆拆成 profile、summary、episodic traces、graph facts 等不同形态。

做**缓存 / 推理复用层**，可以看 **LMCache** 和 **vLLM prefix caching**。LMCache 的核心价值是把“可复用文本只 prefill 一次”的能力抽到独立 KV cache 层，甚至不局限于单次前缀；vLLM 官方文档则把 prefix caching 明确成**基于哈希的块级复用**。这两者给你的启发是：应用层要尽量稳定 prefix，服务层要尽量把 prefix 变成可共享的 cache artifact。

### 4) 我建议的改进方案：SPLIT-Memory

基于上面的官方文档 + 论文 + 开源实现，我建议的 agent 记忆层是 **SPLIT-Memory**：

**S — Stable Prefix Layer**
 把 system prompt、固定工具 schema、组织规则、少量 pinned memory 固定在最前面。这里的原则是：**这部分尽量一字不改**。这样能同时兼容 OpenAI/Anthropic 的精确前缀缓存，也最大化 DeepSeek/GLM/MiniMax 这类隐式缓存的命中。

**P — Persistent Tiered Memory**
 把记忆分成四层：
 `Pinned`（不能丢的规则/约束）
 `Semantic`（长期事实/偏好）
 `Episodic`（事件、决策、任务轨迹）
 `Working`（最近若干轮原文）
 这个分层和 MemoryOS / CFGM / MemoryAgentBench 的方向是一致的，但我把它进一步做成“适配多 provider 的 prompt injection policy”。

**L — Lossy Delta Compaction**
 不要重写整个历史；只把**旧的动态中段**压成 delta summary，并抽取 durable memory。这样做比“每轮重写整段 summary”更不容易打破缓存前缀，也更符合 Anthropic / OpenAI server-side compaction 的思想。

**I — Isolated Dynamic Tail**
 最新用户输入、最近几轮、多变的 tool outputs 一律后置。`Don't Break the Cache` 的结果非常支持这一点：动态 tool result 不应该污染可复用前缀。

**T — Tenant-safe Namespace**
 缓存 namespace 与 memory namespace 都要单独设计。这个想法不仅来自多租户工程经验，也和 Graphiti 的 graph namespacing、OpenAI `prompt_cache_key` / Kimi cache key / vLLM hash-style block reuse 的工程习惯一致。

### 

## 实现要点

### 最大程度命中缓存

- 稳定 prefix 指纹：对 stable prefix 求 hash，生成 provider-specific cache namespace。
- 工具清单 hash：把 tools 变为稳定 manifest，避免频繁改动 JSON schema 打爆缓存。
- 动态内容后置：用户输入、工具返回、临时 scratchpad 只出现在尾部。
- 不重写前缀：压缩只针对旧动态区，不改系统提示和长期规则。

### 最大程度保留记忆

- 显式分层：Pinned > Semantic > Episodic > Working。
- 规则式写入策略：从对话中提取 preference / fact / task / decision / constraint / artifact / environment。
- Delta summary：把旧消息压成一个 continuity summary，保留上下文连续性。
- 检索注入：按查询相关性从语义记忆与情节记忆中召回，再组合进 prompt。

## 快速开始

```python
from agent_memory import HierarchicalMemoryManager, Message, MessageRole, ToolSchema

manager = HierarchicalMemoryManager(namespace="demo")
manager.set_system_instructions([
    "You are a coding agent.",
    "Prefer deterministic plans and preserve important user constraints.",
])
manager.pin_instruction("Always keep user constraints and project invariants stable in the prefix.")
manager.register_tools([
    ToolSchema(
        name="search_docs",
        description="Search internal docs",
        parameters_json_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
])
manager.ingest_message(Message(role=MessageRole.USER, content="Remember that I prefer concise code and typed Python."))
manager.ingest_message(Message(role=MessageRole.ASSISTANT, content="Noted. I'll prefer concise, typed Python."))

request = manager.prepare_request(
    provider_name="openai",
    model="gpt-5.4",
    user_message="Implement a cache-friendly memory manager.",
)
print(request.pretty_json())
```

运行示例：

```bash
python examples/demo_chat_loop.py
python examples/demo_provider_payloads.py
```

## 注意

这个包是**参考实现**，目标是把“记忆层 + 缓存层 + provider 适配层”的边界理清楚，并提供一套可运行骨架。真正上线时建议再接：

- tokenizer 精确计数
- 向量检索或图记忆检索
- 持久化数据库
- 冲突消解
- 隐私分类与删除日志
- provider SDK 真调用
