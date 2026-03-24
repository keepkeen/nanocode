# MCP Polyglot Adapter

一个“标准 MCP + 多厂商适配层”的完整 Python 示例工程。

它做了三件事：

1. **实现一个最小可用的 MCP 工具服务器内核**  
   - `initialize`
   - `notifications/initialized`
   - `ping`
   - `tools/list`
   - `tools/call`

2. **提供一个具体的 MCP 工具实现**
   - `weather.get_current_weather`

3. **把同一套工具定义适配到不同厂商的官方格式**
   - OpenAI Responses API 原生 MCP
   - Anthropic Messages API 原生 MCP Connector
   - DeepSeek Tool Calls / Function Calling
   - GLM Function Calling
   - MiniMax Function Calling（以及官方 MCP 能力说明）
   - Kimi Tool Use / builtin_function

## 目录结构

```text
mcp_polyglot/
├── README.md
├── pyproject.toml
├── mcp_polyglot/
│   ├── __init__.py
│   ├── core/
│   │   ├── protocol.py
│   │   ├── server.py
│   │   └── tool.py
│   ├── adapters/
│   │   ├── base.py
│   │   ├── openai_adapter.py
│   │   ├── anthropic_adapter.py
│   │   ├── openai_compat_adapter.py
│   │   ├── deepseek_adapter.py
│   │   ├── glm_adapter.py
│   │   ├── minimax_adapter.py
│   │   └── kimi_adapter.py
│   └── examples/
│       ├── weather_tool.py
│       ├── demo_protocol.py
│       ├── demo_requests.py
│       └── fastapi_server.py
```

## 安装

```bash
pip install -e .
# 若要运行 FastAPI 远程 MCP 示例：
pip install fastapi uvicorn
```

## 运行示例

### 1) 演示标准 MCP 协议流

```bash
python -m mcp_polyglot.examples.demo_protocol
```

### 2) 生成各厂商请求体

```bash
python -m mcp_polyglot.examples.demo_requests
```

### 3) 启动一个远程 MCP Server（Streamable HTTP 风格）

```bash
uvicorn mcp_polyglot.examples.fastapi_server:app --host 0.0.0.0 --port 8000
```

然后可以用 POST `http://127.0.0.1:8000/mcp` 发送 JSON-RPC 消息。

## 设计说明

### A. 为什么拆成“标准层 + 适配层”

不同厂商官方文档里，MCP/工具调用分成三类：

- **原生远程 MCP**：OpenAI、Anthropic
- **官方 MCP 服务器 / 客户端生态支持，但 API 主接口仍以 Tool Calling / Function Calling 为主**：GLM、MiniMax
- **公开 API 文档主要是 OpenAI 兼容工具调用，不是原生远程 MCP API**：DeepSeek、Kimi

所以工程里分两层：

- `core/`：只表示**标准 MCP 工具定义 / 调用 / JSON-RPC 处理**
- `adapters/`：把同一份工具定义转换成各家需要的请求格式

### B. 统一抽象

- `BaseMcpTool`：单个 MCP 工具抽象基类
- `BaseMcpServer`：MCP Server 基类，负责注册工具、列工具、调工具、处理 JSON-RPC
- `BaseProviderAdapter`：厂商适配器基类
- `OpenAICompatibleFunctionAdapter`：DeepSeek / GLM / MiniMax / Kimi 这类 function-calling 兼容厂商的公共父类

### C. 重要结论

- **OpenAI**：推荐直接走原生 `type="mcp"`。
- **Anthropic**：推荐直接走 `mcp_servers + mcp_toolset`。
- **DeepSeek / GLM / Kimi / MiniMax(Function Calling)**：建议把 MCP tool definition 转成各家函数工具 schema。
- **Kimi** 额外有 `builtin_function`，但这是 Kimi 内置工具，不是通用 MCP tool schema。
