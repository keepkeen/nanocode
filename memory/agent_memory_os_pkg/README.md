# Agent Memory OS v2

一个面向 Agent 的“第一性原理”记忆系统参考实现。

核心观点：

1. **事件流是真相**：所有对话、工具结果、观察都先进入 append-only event log。
2. **记忆块是派生视图**：偏好、事实、约束、决策、任务状态是从事件中抽取出来的 block，不直接等于原始对话。
3. **向量 / 图不是记忆本体**：它们只是检索通道（channel），不是 source of truth。
4. **Prompt 只是编译结果**：每次请求都把控制面、检索面、执行面重新编译为 provider-specific payload。
5. **缓存优先靠稳定前缀，不靠大而全上下文**：静态块 canonicalize 后前置，动态块尾置。
6. **压缩必须可逆**：对 prompt 进行压缩，但不丢事件流；summary 只是一个引用旧事件的可恢复视图。

## 新机制：BLOC Memory OS

- **B**lock-DAG Control Plane：稳定规则、工具 manifest、持久偏好以内容寻址 block 形式存在。
- **L**edger of Observations：所有用户消息、assistant 响应、tool 结果进入 event log。
- **O**mnichannel Retrieval：lexical + pseudo-vector + temporal-graph + salience + recency 融合检索。
- **C**ache-safe Context Compiler：按 provider 的缓存规则把 block 编译成最小高信号上下文。

## 为什么这比“LLM 抽取器 + 向量库 + 图库 + SDK”更接近最优

- 先把“真相层”和“服务层”分开：event log 不丢，memory view 可改。
- 向量检索只适合模糊语义，图检索只适合关系传播，二者都不是全能索引。
- 真正影响延迟和成本的常常不是检索精度，而是 **prefix cache 是否稳定**。
- 执行状态（plan、todo、cursor、open file handles）不应该和长期语义记忆混在一起。
- 压缩不应该覆盖历史事实，而应生成引用源事件的 delta summary。

## 目录

- `agent_memory_os/models.py`：核心类型定义。
- `agent_memory_os/base.py`：抽象类。
- `agent_memory_os/utils.py`：标准化、哈希、稀疏向量等工具。
- `agent_memory_os/store.py`：事件源存储与 block 管理。
- `agent_memory_os/writer.py`：第一性原理 memory writer。
- `agent_memory_os/indexing.py`：混合检索（lexical / vector / graph）。
- `agent_memory_os/compaction.py`：可逆 delta 压缩。
- `agent_memory_os/compiler.py`：缓存安全的上下文编译器。
- `agent_memory_os/orchestrator.py`：统一 Agent Memory OS。
- `agent_memory_os/providers/`：各 provider 适配器与 runtime。
- `agent_memory_os/claude_code.py`：导出 `CLAUDE.md` / `MEMORY.md`。
- `examples/`：示例。

## 支持的 Provider

- OpenAI Responses API
- OpenAI Chat Completions
- Anthropic Messages API（prompt caching + compaction）
- DeepSeek Chat Completions
- GLM Chat Completions
- Kimi Chat Completions + Context Caching
- MiniMax native(OpenAI-compatible chat) + Anthropic-compatible
- Claude Code memory files

## 快速开始

```python
from agent_memory_os import AgentMemoryOS, Message, MessageRole, ToolSchema

osys = AgentMemoryOS(namespace="demo")
osys.set_system_policies([
    "You are a production coding agent.",
    "Prefer minimal diffs, typed Python, and explicit reasoning summaries.",
])
osys.add_user_instruction("Always preserve user constraints and keep cache-stable prefix unchanged.")
osys.register_tools([
    ToolSchema(
        name="search_docs",
        description="Search documentation",
        parameters_json_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
])

osys.observe(Message(role=MessageRole.USER, content="Remember that I prefer concise typed Python."))
osys.observe(Message(role=MessageRole.ASSISTANT, content="Understood. I will prefer concise typed Python."))

req = osys.prepare_request(
    provider_name="openai_responses",
    model="gpt-5.4",
    user_message="Design a cache-safe memory subsystem.",
)
print(req.pretty_json())
```

运行示例：

```bash
python examples/demo_research_grade_memory.py
python examples/demo_provider_calls.py
```
