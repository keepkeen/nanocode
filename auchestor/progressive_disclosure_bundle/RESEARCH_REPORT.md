# Agent 渐进式披露（Progressive Disclosure）调研与实现报告

冻结日期：2026-03-23（America/Los_Angeles）

## 1. 执行摘要

这份调研的结论可以压缩成一句话：

> **高质量 agent 的渐进式披露，不是“默认展示更多”，而是“默认只展示最稳定、最有决策价值的一层；当风险、阻塞、低置信度、外部副作用或用户请求出现时，再进行确定性的逐级展开”。**

从 Codex、Claude Code、Droidrun、OpenCode、Cline、OpenHands、SWE-agent、Aider、Goose、Plandex、Cursor、Vercel AGENTS/Skills 这些系统中，可以提炼出两个彼此互补的成功模式：

1. **稳定地图（Stable Map）模式**：把项目约束、能力边界、关键入口和规则压缩成一个很短、常驻、稳定的索引层，始终放在 agent 可见范围内。
2. **动态发现（Dynamic Discovery）模式**：只把细节、长文档、trace、长工具输出、深层引用放到按需拉取的层级里，让 agent 或用户在需要时再展开。

最优实践不是二选一，而是二者叠加：

- **层 0：任务确认（ACK）**
- **层 1：计划与风险（PLAN）**
- **层 2：当前步骤（STEP）**
- **层 3：证据 / 验证 / diff / 引用（EVIDENCE）**
- **层 4：原始日志 / tool trace / 长输出（TRACE）**

高质量实现应该具备：

- 事件驱动，而不是自由发挥的“碎碎念”式 narration
- 风险感知与审批门控
- 证据优先，trace 后置
- 针对 audience 的自适应渲染
- 新颖性抑制（novelty gate），避免重复刷屏
- 把“静态地图”和“深层文档”彻底分层
- 把“对用户的说明”与“对调试者的 trace”彻底解耦

本报告附带了一套完整、可运行、适度抽象、便于集成到任何 agent harness 中的 Python 实现。

---

## 2. 调研范围与方法

### 2.1 覆盖对象

本次调研覆盖三类材料：

1. **产品 / 开源项目 / 官方工程文章**
   - Codex CLI / harness engineering
   - Claude Code
   - Droidrun
   - OpenCode
   - Cline
   - OpenHands / CodeAct / Runtime / SDK
   - SWE-agent
   - Aider / Goose / Plandex
   - Cursor agent 工程文章
   - Vercel AGENTS.md / Skills

2. **顶会顶刊 / 高质量论文与研究文章**
   - Progressive Disclosure 经典研究
   - CHI / CSCW / UIST / COLING / NAACL / ACL Findings / ICLR / Nature Machine Intelligence 等

3. **X / Twitter 上的高质量实践讨论与延伸文章**
   - Karpathy 关于 agent 协作与代码可审阅性的观点
   - 面向大代码库的规则 / grounding / always-attach context 的经验
   - harness engineering 从 prompt/context engineering 演化出来的工程视角

### 2.2 评估维度

每个项目都按下列维度分析：

- 开放性（是否真开源、开源到哪一层）
- 主要目标场景
- 运行时架构（单 agent / 多 agent / planner-worker / tool runtime）
- 上下文策略（静态上下文、动态检索、技能系统、文件式引用）
- 渐进式披露策略
- 对我们实现的直接启发

---

## 3. 项目调研结果

## 3.1 Codex CLI / OpenAI Harness Engineering

### 观察

Codex CLI 是 terminal 内运行的 coding agent，强调本地工作流、工具调用与 agent-first 的工程实践。OpenAI 在 2026-02 发布的 harness engineering 文章，是这一代 agent UX 与工程约束设计的重要一手资料。

### 关键启发

1. **不要给 agent 一份巨大的总说明书**。
   - OpenAI 明确写到，一份巨大的 `AGENTS.md` 会失败；更有效的做法是一个很短的 `AGENTS.md` 作为目录与地图，把深入内容链接到更细的文档。
   - 这是“渐进式披露”的工程等价物：**默认加载索引，不默认加载细节**。

2. **长期运行 agent 需要 observability**。
   - 日志、指标、trace、浏览器监控、任务持续数小时，这些都意味着：
   - 用户视图与运维视图不能混为一谈。
   - 原始 trace 应被保留，但不应总是打到主界面。

3. **map 比 manual 更重要**。
   - “给一张地图，而不是 1000 页说明书”意味着第一层披露的职责不是把所有信息说完，而是帮助 agent 和用户迅速建立方向感。

### 对渐进式披露的结论

Codex 路线告诉我们：

- 第一层：任务已接收、目标、边界、下一步
- 第二层：短计划 + 风险 + 入口点
- 深层：具体文档、测试、日志、长输出

这正是本实现里 “ACK → PLAN → EVIDENCE/TRACE” 设计的来源之一。

---

## 3.2 Claude Code

### 观察

Claude Code 是 Anthropic 的 coding agent 产品，官方页面强调其通过 agentic search 快速理解代码库。需要注意的是：**公开 GitHub 仓库主要是 Claude Code 的插件和周边能力，不应误判为“完整核心 runtime 已完全开源”**。

### 关键启发

Claude Code 的价值更多体现在产品交互思路：

- 先快速建立代码库理解
- 通过搜索、定位、解释形成可操作上下文
- 将 agent 的“阅读行为”前置

### 对渐进式披露的结论

Claude Code 说明：

- 在代码 agent 里，**解释代码 / 定位代码 / 搜索代码** 本身就是披露的一部分。
- 不是只有“做了什么”要披露，**“我为什么认为这几个文件相关”** 也应该以较短方式呈现给用户。

因此，在本实现中，`EvidenceRef` 不只服务于测试证据，也服务于：

- 计划依据
- 相关文件选择依据
- 不确定性信号

---

## 3.3 Droidrun

### 观察

Droidrun 是高质量的移动端 agent 系统，覆盖 Android / iOS，支持多 provider、截图分析、CLI 调试、分层 agent 体系、structured output，以及 Phoenix / Langfuse 等 tracing。

### 关键启发

1. **层级 agent 系统天然需要披露层级化**。
   - 当 planner、executor、UI observer、tool caller 不同角色并存时，用户不可能同时阅读所有内部状态。

2. **移动端任务特别需要“证据型披露”**。
   - 因为任务结果依赖视觉状态、界面元素、截图、交互轨迹。
   - 所以对用户最有价值的不是完整内部思维，而是“我看到了什么 UI 状态，因此决定点击什么”。

3. **trace 是调试者资产，不该默认倾倒给终端用户**。
   - Droidrun 明确区分了监控 / 调试层与执行层，这与渐进式披露的“证据先于 trace”非常一致。

### 对渐进式披露的结论

如果 agent 有多模态、跨设备或复杂工具链：

- 默认披露：目标、当前 UI 观察、下一步
- 升级披露：截图证据、控件定位依据、关键 tool invocation 摘要
- 深层披露：原始 trace、长日志、分层 agent 间消息

---

## 3.4 OpenCode

### 观察

OpenCode 明确定位为 100% open source、provider-agnostic、支持 agent、自定义权限、LSP 等。它的文档中非常重要的一点是：

- 有 `build` / `plan` 等 primary agent
- plan agent 可用于仅分析而不修改
- 权限可配置为 allow / ask / deny，并支持细粒度规则与按 agent 覆盖

### 关键启发

OpenCode 是“渐进式披露 + 权限门控”最适合作为实现参考的项目之一：

1. **披露层级应和权限系统联动**。
2. **plan agent 与 execution agent 的输出应该天然分层**。
3. **分析层可见，修改层需升级披露并触发 ask/approval**。

### 对渐进式披露的结论

OpenCode 最值得借鉴的点是：

- 计划阶段默认可见
- 修改前自动升级信息层级
- 每个 agent 角色可以有不同的披露模板

本实现里 `APPROVAL_REQUIRED`、`require_approval`、以及按 `ActionKind` 决定升级，直接受这一路线影响。

---

## 3.5 Cline

### 观察

Cline 强调 IDE 内的 autonomous coding，但“每一步都可请求权限”、并可显示 token/cost 等信息。

### 关键启发

Cline 的交互逻辑揭示：

- 成本、权限、动作类型，本身都是渐进式披露的重要输入变量。
- 用户在“看不懂内部链路”的情况下，至少应该知道：
  - 现在要动哪里
  - 为什么要动
  - 代价和风险是什么

### 对渐进式披露的结论

高质量披露不能只有自然语言描述；还需要结构化字段：

- action kind
- target
- cost/token（可选）
- changed files
- approval needed

---

## 3.6 OpenHands / CodeAct / Runtime / SDK

### 观察

OpenHands 已形成相当完整的运行时与 agent 生态：

- Runtime 负责 bash / browser / filesystem / plugins 等动作执行
- CodeAct 采用统一 action space
- SDK 在 2025-11 开源后，支持开发者自定义 workflows 与 tool 列表
- CodeAct 2.1 在 SWE-bench Verified 上给出了较强结果

### 关键启发

1. **统一 action space 使披露更容易标准化**。
   - 只要动作类型是标准化的，渐进式披露就能从 event/phase/action 中稳定地推导，而不是每个 agent 自己写一套文案。

2. **runtime 与 agent 分离，有利于把 disclosure 做成横切层（cross-cutting layer）**。
   - 这正是本实现的核心架构：
   - disclosure engine 不依赖具体模型
   - 不依赖具体工具
   - 不依赖具体 UI
   - 只依赖 typed event + typed state snapshot

3. **代码 agent 的真正关键不是“会不会说”，而是“有没有统一状态机与统一动作语义”**。

### 对渐进式披露的结论

如果想把渐进式披露做成 agent 的“基础设施”，就必须：

- 把 event schema 类型化
- 把 action schema 类型化
- 把 risk / phase / confidence 类型化
- 把 renderer 与 sink 解耦

---

## 3.7 SWE-agent

### 观察

SWE-agent 在研究与 benchmark 维度非常重要，虽然最新文档说明更简化的 mini-swe-agent 已逐步替代原始形态，原仓库趋于 maintenance-only，但它依然代表了研究型 coding agent 的结构化配置范式。

### 关键启发

SWE-agent 证明：

- 配置驱动的 agent 行为很重要
- 复杂 benchmark 能把“代理会做事”和“代理会稳定地把事情做对”区分开

### 对渐进式披露的结论

渐进式披露不应仅凭 UI 灵感设计，它应该被纳入评估 harness：

- 用户是否能及时发现风险
- 用户是否能在关键时刻介入
- 用户是否能复盘 agent 为什么做错

---

## 3.8 Aider / Goose / Plandex

### 观察

这些项目共同说明：

- 终端型 coding agent 仍然是强需求
- 大任务需要上下文压缩、diff review、沙箱、扩展工具集
- 用户并不总希望“全自动黑盒”

### 对渐进式披露的结论

终端 agent 的披露最好遵循：

- 先给非常短的文字摘要
- 再给 diff / file list / test result
- 最后才是长 trace

这也印证了 Karpathy 对“可保持在脑中、可审阅的小块结果”的偏好。

---

## 3.9 Cursor：长程并发 agent、动态上下文发现

### 观察

Cursor 在 2026-01 / 2026-02 发布的一系列工程文章，是当前 agent runtime 设计最值得重视的公开材料之一：

- 多 agent 并发时，flat coordination + 锁会失败
- planner / worker 结构更可靠
- intent 说明必须非常明确
- 对每一步都追求 100% correctness 会拖垮吞吐
- 更少 upfront details，让 agent 动态拉取上下文，通常更优
- 工具长输出可写入文件，再按需引用
- skills 以文件形式组织
- 只保留一个小而稳定的静态上下文层描述工具名和能力
- 启用 MCP 工具时，A/B test 总 token 降低 46.9%

### 关键启发

Cursor 几乎直接定义了现代渐进式披露的运行时原则：

1. **静态上下文只保留“能力地图”**。
2. **细节不要 upfront 堆满，而是通过动态发现拉取**。
3. **长输出不要塞进主对话，写入文件 / 外挂引用**。
4. **多 agent 需要 planner-worker 披露分层，而不是把所有消息流平铺给用户**。

### 对渐进式披露的结论

Cursor 路线非常适合转译为系统设计：

- 主视图只展示小而稳定的信息块
- 深度信息进入引用层 / 文件层 / trace 层
- 允许用户“下钻”而不是强迫用户“预读”

---

## 3.10 Vercel AGENTS.md / Skills

### 观察

Vercel 在 2026-01 的 AGENTS.md 与 Skills 文章，是目前“静态索引 + 按需展开”路线最明确的公开表达之一：

- 通过压缩到约 8KB 的 AGENTS.md 索引，在 API eval 上表现很好
- passive context（直接给短索引）优于让 agent 决定要不要主动检索的 active retrieval
- skill 的本质是：启动时加载轻量索引，命中后再加载完整技能
- references 目录明确用于按需引用

### 关键启发

Vercel 给出的不是单纯 prompt 技巧，而是一套信息分层范式：

- **常驻层**：很小、很稳、无需判断是否要读
- **技能层**：识别到匹配场景时再加载
- **引用层**：长文档、操作手册、细节资料按需展开

### 对渐进式披露的结论

这几乎可以直接被翻译成 agent UX：

- 始终可见：目标、短规则、能力边界、入口文件、关键命令
- 条件可见：plan、验证证据、审批原因
- 按需可见：trace、长工具输出、引用文档全文

---

## 4. 顶会顶刊 / 高质量研究结论

## 4.1 Progressive Disclosure 经典研究

关于 Progressive Disclosure 的研究表明，用户常常会从**一开始更简化、更少认知负担的反馈**中获益。尤其在系统可能出错、用户需要建立工作启发式的时候，信息不应一次性倾倒。

### 对 agent 的启发

这直接反对“把完整 chain、所有日志、所有细节都先吐出来”的设计。对 agent 来说，更优的做法是：

- 默认先给低认知负担的决策层信息
- 让更深的解释 / 错误来源 / 原始 trace 延后展开

---

## 4.2 AI 设计 agent 的过程透明度研究（CSCW 2025）

有关 AI design agents 的研究表明，透明度不是越高越好，而是要和任务、用户预期、界面负担相匹配。低 / 中 / 高透明度会显著影响信任、满意度与使用意愿。

### 对 agent 的启发

渐进式披露本质上就是：

- 不是追求“最大透明度”
- 而是追求“**恰当透明度**”

因此系统必须具备：

- audience-aware
- task-aware
- risk-aware
- uncertainty-aware

---

## 4.3 RADI（2025）：关系式、自适应披露

RADI 的重要启发在于：披露不应该是固定模板，而应随着用户角色、任务关系和上下文发生变化。

### 对 agent 的启发

这支持我们把策略抽象成 `AbstractDisclosurePolicy`，并让渲染与策略解耦：

- 给 end user 的披露
- 给 developer 的披露
- 给 reviewer / operator 的披露

应该是同一状态源上不同视图，而不是互相复制的不同逻辑分支。

---

## 4.4 Plan-Then-Execute（CHI 2025）

该研究指出，先规划再执行能够提升用户 agency、降低认知负担，但 agent 规划也可能是双刃剑：计划质量、用户是否被正确地纳入校准过程，决定了最终体验。

### 对 agent 的启发

这意味着：

- 计划本身应成为第一类披露对象
- 但不应强迫用户先阅读一大篇 plan
- 最好的方式是：
  - 给短 plan
  - 给风险与假设
  - 给下一步
  - 允许展开更细节

---

## 4.5 Multi-agent transparency（Nature Machine Intelligence, 2026）

多 agent 系统需要透明性，原因并不只是“伦理层面的可解释性”，而是为了避免浪费计算资源和人类协作成本。

### 对 agent 的启发

在 multi-agent 体系中：

- 内部协作不应该全部暴露
- 但用户必须知道：
  - 谁负责计划
  - 谁负责执行
  - 谁负责验证
  - 当前阻塞在哪一层

因此，高质量披露应该支持 role-specific summary。

---

## 4.6 Tool planning / orchestration / multi-agent 论文线索（NAACL / ACL Findings / ICLR 2026）

近期高质量工作共同强调：

- 工具调用规划不能只靠贪心 react
- 工作流规划与约束执行很关键
- 角色分工（planner / coder / verifier）是有效方向
- 真实世界 benchmark 必须项目级、长期、带自动评估

### 对 agent 的启发

渐进式披露应该围绕以下几个“真实世界关键点”设计，而不是围绕漂亮文案：

- constraint awareness
- planner / executor / verifier 分层
- project-level evidence
- long-run recoverability
- benchmarkable observability

---

## 5. X / Twitter 与 harness engineering 讨论的提炼

## 5.1 Karpathy：不想要 20 分钟消失后扔回来 1000 行代码

Karpathy 的观点非常适合作为 agent 渐进式披露设计的用户侧北极星：

- 不希望 agent 消失很久后一次性给回巨量代码
- 希望结果以自己能保持在脑中的小块给出
- 希望模型解释其写的代码
- 希望模型拿出 API 文档与正确性依据
- 希望在不确定时协作、提问，而不是擅自假设

### 提炼

这几乎直接定义了优秀 coding agent 的披露目标：

- 分块
- 可审阅
- 解释伴随生成
- 证据伴随结论
- 不确定时升级交互，而不是闷头继续

---

## 5.2 大代码库中的 grounding / rules / always-attach context 经验

X 上关于大代码库使用 Cursor 等 agent 的高质量经验总结里，反复出现的主题是：

- 给项目结构地图
- @ 关键文件与目录
- 用规则让 agent 知道 primitives 和架构边界
- 将反复出现的经验沉淀为长期规则
- 让“总是附带”的规则不要在长对话中丢失

### 提炼

这说明：

- 优秀披露并不只是“对人展示”，也是“对 agent 稳定暴露项目约束”
- 用户与 agent 共享的短规则层，是 agent 成功率的基础设施

---

## 5.3 Harness engineering：从 prompt 到 context，再到 harness

近期对 harness engineering 的讨论，本质上强调的是：

- 工程师的价值逐渐从“写每一行代码”转向“设计约束、反馈回路、验证系统、环境与守护机制”
- 重点从 prompt wording，转向 system / runtime / observability / validation

### 提炼

对于渐进式披露，这意味着：

- 渐进式披露不该只是 UI 组件
- 它必须是 harness 的一部分
- 它应该由事件、验证、审批、trace、恢复策略共同驱动

---

## 6. 总体设计结论：agent 渐进式披露应该怎么写

## 6.1 核心原则

### 原则 1：默认只展示最小稳定层

默认层应足以回答：

- 我收到什么任务？
- 我准备怎么做？
- 当前在做什么？
- 下一步是什么？

但不应把所有日志和细节塞满。

### 原则 2：风险升级必须可预测

当发生以下情况时，披露必须升级，而不是“模型想不想说都行”：

- 写文件
- 执行命令
- 网络访问
- 外部副作用
- 不可逆操作
- 低置信度
- 错误 / 阻塞
- 用户显式要求细节

### 原则 3：证据优先于 trace

对大多数用户，最有价值的是：

- 哪些文件改了
- 哪些测试过了 / 没过
- 为什么选这些文件
- 哪个文档支持这个改动

而不是 300 行原始 trace。

### 原则 4：叙述与运行时解耦

渐进式披露必须由一个独立层处理：

- 上游 agent 只负责发事件
- disclosure engine 负责决定发什么层级
- renderer 决定怎么展示
- sink 决定发到哪里

### 原则 5：去噪比多说更重要

用户最怕两件事：

- 完全黑盒
- 高频重复噪声

所以必须有 novelty gate / rate limiting。

---

## 6.2 推荐的五层披露模型

### L0 — ACK

用途：接任务、保持方向感

字段：

- goal
- immediate next step

### L1 — PLAN

用途：建立用户控制感与任务边界

字段：

- goal
- short plan
- risks / assumptions
- next step

### L2 — STEP

用途：持续性但低负担的进度可见性

字段：

- current action
- target
- short rationale
- next step

### L3 — EVIDENCE

用途：在关键点提供决策依据与验证依据

字段：

- evidence refs
- changed files
- tests
- uncertainty signals
- approval context

### L4 — TRACE

用途：调试、复盘、深挖

字段：

- raw logs
- tool invocations
- long outputs
- trace fragments
- retry trail

---

## 6.3 推荐的升级触发器

建议使用明确规则，而不是模糊 prompt：

1. `TASK_STARTED` → ACK 或 PLAN
2. `PLAN_CREATED` / `PLAN_UPDATED` → PLAN
3. `ACTION_STARTED` + consequential action → EVIDENCE（必要时 approval）
4. `ACTION_COMPLETED` + verification material → EVIDENCE
5. `ERROR` / `STALLED` → EVIDENCE 或 TRACE
6. `DEEP_DIVE_REQUESTED` → TRACE
7. `SUMMARY_REQUESTED` → EVIDENCE
8. `TASK_COMPLETED` → EVIDENCE（可选 TRACE）

---

## 6.4 典型反模式

1. 巨大的单文件系统提示 / 单体 AGENTS
2. 一上来就倾倒所有细节
3. 每个 step 都展示完整 trace
4. 无审批地跨越写文件 / 执行命令 / 外部动作
5. 出错后只显示“失败了”，不说明恢复策略
6. 长时间沉默，最后扔出大 diff
7. 把用户说明与 operator trace 混在一个视图里

---

## 7. 创新性优化方案

下面给出一个在现有公开实践基础上，进一步优化后的方案。

## 7.1 双平面上下文（Dual-Plane Context）

### Plane A：稳定地图层

始终常驻，极短：

- repo / task short map
- 关键规则
- 入口文件
- 核心命令
- 能力边界

### Plane B：按需展开层

只在匹配或用户请求时展开：

- 深文档
- 详细技能说明
- 长日志
- 原始输出
- 历史总结

### 创新点

它把 Vercel 的 passive context + Cursor 的 dynamic discovery 融合起来：

- 不让 agent 决定“要不要先知道最基本的地图”
- 也不让静态上下文被细节撑爆

---

## 7.2 证据优先型披露（Evidence-First Disclosure）

对大多数高风险步骤，不先弹 trace，而先弹：

- 依据文档
- 相关文件
- 测试范围
- 不确定性说明
- 预计动作

### 创新点

这比“显示推理过程”更实用，因为用户更容易审查“依据是否合理”，而不是阅读大量内部想法。

---

## 7.3 事件驱动状态机（Event-Driven Disclosure FSM）

把渐进式披露从 prompt 技巧升级成 runtime 策略：

- 输入：event + state + risk + phase + preferences
- 输出：level + sections + evidence/trace flags + approval requirement

### 创新点

这让披露具备可测试性、可 benchmark 性、可替换性。

---

## 7.4 Audience-aware 渲染

同一条状态，对不同角色渲染不同：

- end user：面向结果、风险、下一步
- developer：增加 changed files、evidence refs、cost
- reviewer：强调 diff、tests、validation
- operator：强调 trace、retries、tool health

### 创新点

将 RADI 的适应性披露思想落到代码层。

---

## 7.5 Novelty Gate + 强制升级通道

- routine updates 走时间间隔 + 指纹去重
- error / approval / explicit deep dive / completion 强制放行

### 创新点

它同时解决两类失败：

- agent 太吵
- agent 该说时不说

---

## 7.6 验证驱动闭环（Verifier-Centric Loop）

建议在真实系统中继续扩展：

- verifier 产出结构化验证项
- disclosure engine 自动把这些验证项编织进 EVIDENCE 层
- 失败时直接映射到 recovery summary

### 创新点

把 harness engineering 里“验证比生成更重要”的思想转成 UX 资产。

---

## 8. 完整代码实现说明

附带代码位于：

- `src/progressive_disclosure/domain.py`
- `src/progressive_disclosure/events.py`
- `src/progressive_disclosure/abstractions.py`
- `src/progressive_disclosure/novelty.py`
- `src/progressive_disclosure/providers.py`
- `src/progressive_disclosure/policies.py`
- `src/progressive_disclosure/renderers.py`
- `src/progressive_disclosure/sinks.py`
- `src/progressive_disclosure/engine.py`

以及：

- `examples/demo.py`
- `tests/test_engine.py`

## 8.1 抽象层设计

### `AbstractDisclosurePolicy`

职责：

- 根据 event + context 计算应该披露什么层级
- 决定是否带 evidence / trace
- 决定是否需要 approval

### `AbstractEvidenceSelector`

职责：

- 从 action refs、plan、changed files、不确定性里抽取最值得展示的证据

### `AbstractTraceProvider`

职责：

- 在被允许和需要时，提供 trace 片段

### `AbstractRenderer`

职责：

- 将结构化 decision 渲染成 markdown / structured payload

### `AbstractEventSink`

职责：

- 将 disclosure message 发送到 stdout、内存、聊天 UI、WebSocket、数据库等

### `AbstractNoveltyGate`

职责：

- 做节流和去重

---

## 8.2 基类与核心实现

### `AdaptiveProgressiveDisclosurePolicy`

这是默认策略实现，内置以下规则：

- 任务开始：高风险 / 中风险默认给 PLAN
- 计划变更：给 PLAN
- 审批点：强制给 EVIDENCE + approval
- 错误：给 EVIDENCE 或 TRACE
- 后果性动作：写文件 / 执行 / 网络 / 不可逆操作时升级披露
- 低置信度、changed files 多、验证型动作完成时，升级到 EVIDENCE

### `TimeAndNoveltyGate`

功能：

- 通过 event + level + step + action + title 生成指纹
- 重复消息自动抑制
- trace / approval / important events 可强制放行

### `MarkdownRenderer`

把最终消息渲染成：

- summary
- sections（mission / plan / current_action / risk / evidence / trace / next_step）

### `ProgressiveDisclosureEngine`

执行链路：

1. 接收 `AgentEvent`
2. 合并到 `DisclosureContext`
3. 调用 policy 产出 decision
4. novelty gate 判断是否应该发送
5. 取 evidence / trace
6. renderer 生成最终消息
7. 记录 novelty

### `ProgressiveDisclosureManager`

作为集成入口：

- `handle_event(event, context)`
- 内部用 engine 生成 message
- 再通过 sink 发布

---

## 8.3 为什么这个结构解耦

这个实现刻意做到以下解耦：

1. **与模型解耦**
   - 不依赖 OpenAI / Anthropic / 本地模型

2. **与 agent runtime 解耦**
   - 只要上游能发 event，就能接入

3. **与 UI 解耦**
   - CLI、chat、web、IDE 都能作为 sink

4. **与证据来源解耦**
   - 当前只是 inline selector，未来可接 repo index、trace store、test DB

5. **与策略解耦**
   - 可以针对不同业务场景替换 policy

---

## 9. 如何集成到真实 agent 中

建议按以下方式接入：

### 9.1 在 harness 层定义标准事件

例如：

- 任务进入队列
- 计划生成
- 子 agent 启动
- patch 开始
- tests 开始
- tests 失败
- approval required
- final merge candidate ready

### 9.2 对每个动作打上标准元数据

例如：

- `ActionKind`
- `target`
- `irreversible`
- `external_effect`
- `evidence_refs`

### 9.3 将验证器结果结构化

例如：

- passed tests
- failed tests
- lint status
- benchmark delta
- changed files
- rollback safety

### 9.4 给不同 audience 配不同 renderer/sink

例如：

- 用户聊天框：MarkdownRenderer + ChatSink
- IDE 面板：StructuredRenderer + WebSocketSink
- 运维后台：TraceHeavyRenderer + DB Sink

---

## 10. 进一步可扩展方向

如果要把这套实现继续做成 production-grade，我建议继续补这几块：

1. **Diff-aware Evidence Selector**
   - 从 git diff 中自动提炼影响范围

2. **Verifier Adapter**
   - 统一接 pytest / unit test / benchmark / e2e / static analysis

3. **Role-aware Multi-Agent Disclosure**
   - planner / executor / verifier 独立 summary，再汇总到用户层

4. **File-backed Trace Store**
   - 长 trace 自动落盘，只在主对话中放索引和摘录

5. **Policy Benchmark Harness**
   - 比较不同 disclosure policy 对用户任务完成率 / approval latency / trust calibration 的影响

6. **Human Interrupt Contract**
   - 当用户打断时，系统自动生成“当前状态、可恢复点、下一建议动作”摘要

---

## 11. 最终结论

综合项目、论文和 X 上的高质量讨论，可以得出一个非常稳定的结论：

> **agent 的渐进式披露，最优形态不是“把内部过程都展示出来”，而是“把控制权、审查点、证据和可恢复性，以最小负担的方式持续交给用户”。**

最强方案不是单独模仿某一个项目，而是融合：

- Codex / Vercel 的短索引 / 地图式静态上下文
- Cursor 的动态上下文发现与文件式深层引用
- OpenCode / Cline 的权限与审批门控
- Droidrun / OpenHands 的运行时分层与 trace 解耦
- Progressive Disclosure / RADI / Plan-Then-Execute / Multi-agent Transparency 研究中的自适应透明度原则

最终落地时，应该把“渐进式披露”视为 **agent harness 的核心模块**，而不是对话层的文案装饰。

---

## 12. 参考来源（按主题整理）

### 官方 / 项目 / 工程文章

- OpenAI Codex CLI 官方文档与 GitHub 仓库
- OpenAI《Harness engineering: leveraging Codex in an agent-first world》
- Anthropic Claude Code 官方页面与 GitHub 仓库
- Droidrun GitHub 与官方文档
- OpenCode GitHub 与官方文档
- Cline GitHub 与官网
- OpenHands SDK / Runtime / CodeAct / Blog
- SWE-agent GitHub 与文档
- Aider / Goose / Plandex 官方资料
- Cursor 2026 系列工程博客
- Vercel AGENTS.md 与 Skills / References 文章

### 学术研究

- Progressive Disclosure（ACM, 2020）
- Process Transparency in AI Design Agents（CSCW Companion 2025）
- RADI（UIST Adjunct 2025）
- Plan-Then-Execute（CHI 2025）
- Multi-agent AI systems need transparency（Nature Machine Intelligence, 2026）
- COLING 2025 LLM Agent Survey
- MACT（NAACL 2025）
- Smurfs（NAACL 2025）
- ProjectEval（ACL Findings 2025）
- OrchestrationBench（ICLR 2026）
- AgentFlow / Flow-GRPO（ICLR 2026）
- ToolTree（ICLR 2026）

### X / Twitter 相关讨论与延伸文章

- Karpathy 关于 coding agent 协作方式的 thread
- 面向大代码库 grounding / rules / always-attach context 的经验 thread
- harness engineering / context engineering 相关讨论与转述文章

