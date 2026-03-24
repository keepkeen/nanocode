# Sub-Agent Research & Reference Implementation

This folder contains two deliverables:

1. `research_report.md`: a fresh survey of official vendor docs, recent papers, and open-source projects.
2. `subagent_framework/`: a decoupled Python reference implementation for provider-agnostic sub-agents.

## Design goals

- Keep the **sub-agent contract provider-agnostic**.
- Serialize the same sub-agent definition into **OpenAI / ChatGPT, Claude Code, DeepSeek, GLM, Kimi, and MiniMax** formats.
- Separate **routing**, **memory**, **execution**, and **provider serialization**.
- Include one **concrete sub-agent** (`ResearchSubAgent`) and a runnable demo.

## Quick start

```bash
cd /mnt/data/subagent_research
PYTHONPATH=. python examples/demo_subagent.py
```

This will:

- run a local orchestration demo;
- select the registered sub-agent;
- generate provider-native artifacts into `examples/provider_artifacts.json`.

## File structure

```text
subagent_research/
├── README.md
├── research_report.md
├── examples/
│   ├── demo_subagent.py
│   └── provider_artifacts.json   # generated after running the demo
└── subagent_framework/
    ├── __init__.py
    ├── abstractions.py
    ├── memory.py
    ├── models.py
    ├── orchestrator.py
    ├── router.py
    ├── agents/
    │   ├── __init__.py
    │   └── research_subagent.py
    └── providers/
        ├── __init__.py
        ├── base.py
        ├── claude_code.py
        ├── deepseek.py
        ├── glm.py
        ├── kimi.py
        ├── minimax.py
        └── openai_chatgpt.py
```

## Key implementation ideas

### 1. Canonical sub-agent definition

`SubAgentDefinition` is the single source of truth. Every provider adapter reads from this structure.

### 2. Hierarchical working memory

`HierarchicalWorkingMemory` keeps active observations per subgoal and archives older items into compact summaries.

### 3. Router with pruning

`KeywordCapabilityRouter` scores agents by keyword/capability overlap and only delegates to the strongest specialists.

### 4. Vendor adapters

Adapters do not execute remote APIs by default. Instead, they render **correct request/config shapes** that can be plugged into real SDK calls later.

### 5. Concrete sub-agent

`ResearchSubAgent` is fully implemented and can be orchestrated locally.
