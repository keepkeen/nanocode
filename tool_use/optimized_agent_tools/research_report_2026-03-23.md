# Agent 工具链调研与优化设计（2026-03-23）

## 结论摘要

- 当前高质量 coding/web agent 的主流设计已经明显收敛到：**工具权限显式化、沙箱默认开启或至少可配置、网络与文件系统分层审批、规则文件/策略文件外置、审计日志可追踪**。
- `bash` 的核心不是“能不能执行命令”，而是：**如何在最小可用权限下执行、如何把危险链式 shell 语法与安全子命令分开、如何限制运行时长/输出体积/环境变量/可写路径、如何结合审批策略**。
- `websearch` 的关键不是“接一个搜索 API”，而是：**结果是否可控、是否去重规范化、是否能和 fetch 的 URL provenance 联动、是否支持域名 allow/deny、是否能做缓存和重复调用抑制**。
- `webfetch` 的关键不是“抓网页”，而是：**阻断 prompt injection 与数据外带（exfiltration）路径**。核心手段包括：仅允许用户 URL 或搜索结果 URL；限制重定向；阻断私网/metadata 地址；文本抽取与 query-aware 片段压缩；默认禁掉动态拼接 URL。
- 最有价值的改进方向不是无限增强 agent 自主性，而是：**把 planning、retrieval、execution、policy 四层拆开，并把 policy 前置成第一等公民**。

## 一、项目调研对象

### 1. Codex（OpenAI）
- 终端/CLI coding agent。
- 明确提供 `bash`、文件修改、web search 等能力。
- 安全策略非常成熟：approval policy、sandbox 模式、shell environment policy、规则文件、网络默认关闭/按策略放开。
- 对复合 shell 命令有细粒度风险处理能力。

### 2. OpenCode
- 高星开源 terminal coding agent。
- 原生内置 `bash`、`read`、`edit`、`webfetch`、`websearch`。
- 权限配置是核心：`allow / ask / deny`。
- 有外部目录权限与循环调用防护配置。

### 3. Claude Code（公开仓库部分）
- 官方公开仓库里可以看到大量插件、配置、hooks、settings 示例与文档。
- 设置里能看到对 Bash sandbox、工具 deny、审批行为的支持。
- 但它不等同于完全像 Codex/OpenCode 一样把完整 agent runtime 全部开源出来；更适合作为**产品级安全配置与工具设计参考**。

### 4. OpenHands
- 重点在 Docker Runtime / Sandbox。
- 强调 arbitrary code execution 需要跑在 Docker 里。
- 适合借鉴其**运行环境与工作区挂载模型**。

### 5. Cline
- 明显的人在环设计。
- 命令执行、文件修改、浏览器动作通常都强调显式批准。
- 适合借鉴其**高可控审批与规则/忽略文件机制**。

### 6. Aider
- 更偏 repo pair-programming，而不是重工具自治。
- 核心优势是 git、repo map、编辑工作流，而不是复杂浏览器/搜索/抓取工具。
- 启发：在代码问题上，**定位优先于盲目自治**。

### 7. Goose
- 开源、可扩展、MCP 生态友好。
- 默认自主性比较强，但提供 permission mode、tool permissions、ignore 机制。
- 启发：强自治必须和**更强策略层**一起用。

### 8. DroidRun / DroidAgent
- 不是典型 coding CLI，但对“agent 如何管理执行环境与长链路动作”很有参考价值。
- 启发：执行层要和规划层、环境层分离。

## 二、分模块设计经验

### A. Bash 工具

#### 现状共识
1. **不要默认全能力 shell**。
2. 先做命令级策略判断，再决定是否执行。
3. `shell=True` 只能作为受控例外，默认应走 argv 执行。
4. 要做：
   - cwd 限制
   - writable roots 限制
   - env allowlist
   - timeout
   - output budget
   - privileged command denylist
   - remote write / remote publish / outbound interactive command ask

#### 最值得抄的点
- **Codex 风格**：审批策略 + 沙箱模式 + compound shell 特殊处理。
- **OpenCode 风格**：对工具统一用 allow / ask / deny。
- **OpenHands 风格**：把真正的隔离交给 Docker/OS sandbox，而不是只靠 Python 包装。

### B. WebSearch 工具

#### 应有能力
- provider 抽象层
- 结果 URL 规范化
- 结果去重
- 域名 allow/deny
- session provenance 记录
- 重复调用检测
- 可选缓存

#### 关键优化
- 搜索结果不要原样全塞给模型。
- 对结果只保留必要字段：title、url、snippet、score、published_at。
- 让 fetch 只允许访问“用户给的 URL + 搜索结果 URL”。

### C. WebFetch 工具

#### 安全重点
- URL 中禁止凭据
- 默认阻断 localhost / metadata / 私网
- 限制重定向次数
- 限制下载体积
- 只抽取可见文本
- query-aware 摘要/片段抽取
- provenance check

#### 为什么重要
很多 prompt injection 不是发生在搜索 API，而是发生在抓到的网页内容里。
因此 fetch 应该是 **内容安全边界**，不能只是网络请求函数。

### D. 执行环境 / 沙箱

建议至少分三层：
1. **进程内策略层**：命令/URL/域名/路径/预算/审批
2. **进程封装层**：子进程、IO 截断、超时终止、环境变量清洗
3. **OS 隔离层**：Docker / Firejail / Bubblewrap / gVisor / Firecracker

生产环境优先级：
- Docker / microVM > Firejail/bwrap > 仅 Python 封装

## 三、论文与 benchmark 启发

### 1. 安全/可信评测
- ST-WebAgentBench：说明 web agent 不只是看 task success，还要看 policy compliance、risk ratio 等指标。
- WASP / AgentDojo：说明 prompt injection 是一等问题，不是边角问题。

### 2. 规划与执行解耦
- WebAnchor：第一步 plan 对长链路 web reasoning 影响极大，规划和执行分阶段优化更稳。
- R-WoM：长链路环境模拟很容易漂移，必须引入外部检索或世界模型约束。

### 3. 检索增强
- WebRAGent：retrieval augmentation 对 web agent 确实有效，尤其是 DOM + visual 混合场景。
- CoRAG / 多步检索思想：复杂查询不应只打一枪式搜索。

### 4. 软件工程 agent 反思
- Agentless：很多 repo 任务更需要 localization + repair，而不是长链路自治。
- 对 coding agent 来说，`bash` 不应成为兜底大锤，而应成为受控执行器。

## 四、本文给出的优化方案

### 核心创新点
1. **Policy-first**：工具调用先过 policy，再谈执行。
2. **Provenance-preserving WebFetch**：抓取只允许 user URL 或 search ledger URL。
3. **Query-aware Fetch Compression**：抓网页后不是全文塞模型，而是 query-aware 片段抽取。
4. **Hash-chained Audit**：所有执行都能形成可追踪链式审计日志。
5. **Repeat-call Guard**：防止搜索/抓取/命令陷入循环。
6. **Abstract Base Classes**：provider、tool、sandbox 彻底解耦。

## 五、实现概览

实现目录包含：
- `policy.py`：策略引擎
- `bash.py`：安全 Bash
- `websearch.py`：搜索 provider + 工具封装
- `webfetch.py`：安全抓取
- `sandbox.py`：sandbox 适配
- `audit.py`：hash chain 审计
- `registry.py`：session state / provenance ledger
- `tests/`：单元测试

## 六、适用建议

### 小团队 / PoC
- 先用本文实现
- provider 选 Tavily 或 Brave
- Bash 默认 `allow_shell_compounds=False`
- `require_url_provenance=True`
- `allow_private_network=False`

### 企业内网 / 高安全场景
- 必须接入 Docker / microVM
- 强制 approval policy
- 搜索与抓取做域名 allowlist
- 所有工具写入 hash-chained 审计日志
- 关键命令（git push、deploy、ssh、publish）默认 ask/deny

## 七、结论

真正高质量的 agent 工具链，不是工具更多，而是：
- 策略更前置
- 权限更细
- 执行更可审计
- 搜索/抓取与 provenance 更强绑定
- shell 更少“黑箱”
- 规划、检索、执行、隔离四层更解耦

这也是把开源项目经验与 2025–2026 新论文启发结合后，最值得落地的一条路线。
