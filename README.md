<div align="center">

# 🌉 GLM-2api：您的私人 Z.AI to OpenAI 协议转换桥梁 🚀

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python Version](https://img.shields.io/badge/Python-3.11+-brightgreen.svg)](https://www.python.org/)
[![Docker Support](https://img.shields.io/badge/Docker-Ready-blue.svg?logo=docker)](https://www.docker.com/)
[![Replit Support](https://img.shields.io/badge/Replit-Deploy-orange.svg?logo=replit)](https://replit.com/)

**一个将 Z.AI 的原生 API 巧妙伪装成 OpenAI 标准格式的开源项目，让您心爱的应用无缝接入强大的 GLM 系列模型！**

</div>

---

> “我们不是在编写代码，我们是在构建桥梁。每一行指令，都是通往更广阔世界的一块基石。GLM-2api 不仅仅是一个工具，它是一种信念——相信技术的力量可以打破壁垒，连接思想，让每一个人都能轻松驾驭未来。”

## ✨ 项目缘起：一个美丽的“谎言”

想象一下，您有一个非常棒的应用程序，它说着一口流利的 "OpenAI 语"，但您内心深处却渴望着 Z.AI 家那强大而迷人的 GLM 系列模型。怎么办？难道要让您的应用从头开始学习一门新的语言吗？

不！我们选择了一种更优雅、更具智慧的方式——**创造一个完美的翻译官**。

GLM-2api 就是这个翻译官。它站在您的应用和 Z.AI 服务器之间，将每一个 OpenAI 格式的请求，都实时、无损地翻译成 Z.AI 能听懂的语言；反之，它又将 Z.AI 的回应，精心包装成您的应用所熟悉的 OpenAI 格式。

这，就是一个美丽的“谎言”。您的应用自始至终都以为自己在和 OpenAI 对话，而实际上，它正在享受 GLM 模型带来的澎湃动力！

## 核心特性：您的瑞士军刀 🛠️

*   **🤖 高度兼容 OpenAI**：就像一位语言天才，完美模拟了 `/v1/chat/completions` 接口，支持流式（Streaming）与非流式输出。
*   **🔧 强大的工具调用 (Function Calling)**：赋予模型行动的能力！无论是查询天气、还是执行代码，只需定义好工具，模型就能智能调用。
*   **🧠 “思考”过程全揭秘**：独家支持 Z.AI 的 `Thinking` 模式，让您能“看见”模型思考的每一步，就像给它装上了一个透明的大脑！
*   **🔑 智能令牌池管理**：这不仅仅是一个令牌管理器，更是一位智慧的“钥匙管理员”。它能自动轮换、禁用失效令牌、处理网络波动，确保服务 24/7 稳定在线。
*   **🌐 匿名模式 & 负载均衡**：既能像游客一样获取临时令牌，保护您的隐私；也能通过 Docker Compose + Nginx 组建“克隆军团”，轻松应对高并发请求。
*   **🚀 现代化技术栈**：基于 `FastAPI` + `Granian` 构建，拥有闪电般的性能和异步处理能力。
*   **☁️ 一键部署**：无论您是 Docker 的信徒，还是 Replit 的爱好者，我们都为您准备了“懒人一键部署”方案。

## 🏛️ 宏伟蓝图：它是如何工作的？

这个项目的核心思想是“**转换与适配**”。让我们深入这座桥梁的内部，看看它的精密构造。

<div align="center">
<img src="https://user-images.githubusercontent.com/1234567/123456789-your-diagram-url.png" alt="架构图" width="800"/>
<p><em>上图：GLM-2api 工作流程示意图 (请替换为您的架构图)</em></p>
</div>

1.  **入口与守卫 (`main.py`, `openai.py`)**
    *   **大白话解释**：这是项目的“前门”和“接待员”。`main.py` 使用 `FastAPI` 框架搭建了一个网络服务，而 `app/core/openai.py` 则负责处理所有发往 `/v1/chat/completions` 的请求。它会验证您的身份（API Key），然后将请求转交给“总设计师”。
    *   **技术点**：`FastAPI` 提供了强大的异步处理能力和自动文档生成。`APIRouter` 用于模块化管理路由。`Header` 依赖注入用于获取认证信息。

2.  **总设计师与翻译官 (`zai_transformer.py`)**
    *   **大白话解释**：这是整个项目的灵魂！它接收到 OpenAI 格式的“设计图”（请求），然后 meticulously 地将其转换为 Z.AI 能看懂的“施工图”。模型名称映射、`system` 角色的巧妙处理、工具（Functions）的注入，都在这里完成。
    *   **技术点**：`transform_request_in` 方法是核心，它构建了 Z.AI 需要的复杂 JSON 结构，包括 `features`, `mcp_servers` 等。它还会动态生成浏览器头（`User-Agent`），模拟真实用户行为。

3.  **钥匙管理员 (`token_manager.py`)**
    *   **大白话解释**：想象一个装满了钥匙的保险箱。这位管理员会按顺序分发钥匙（Token），如果发现某把钥匙打不开门（请求失败），他会做个标记，失败几次后就暂时封存这把钥匙。他还会定期检查，看看有没有新的钥匙补充进来。这保证了我们总能用有效的钥匙去开门。
    *   **技术点**：实现了线程安全的令牌轮询（Round-Robin）、失败计数和自动停用/恢复机制。`_lock` 保证了在高并发下数据的一致性。

4.  **施工队与直播员 (`response_handlers.py`, `sse_tool_handler.py`)**
    *   **大白话解释**：当 Z.AI 开始返回数据时，这两位就上场了。Z.AI 的数据是“一块一块”流式返回的（SSE, Server-Sent Events）。
        *   `response_handlers.py` 负责处理常规的文本流，将 Z.AI 的数据块（`chunk`）翻译成 OpenAI 的格式再发给客户端。
        *   `sse_tool_handler.py` 是工具调用的专家。它能从混乱的数据流中，精准地解析出工具调用的意图、名称和参数，即使数据是分段到达的，它也能拼接成完整的指令。
    *   **技术点**：`SSEParser` 用于解析 SSE 流。`SSEToolHandler` 是一个状态机，它通过正则表达式和 JSON 增量解析，实时处理工具调用流，这是实现稳定 Function Calling 的关键。

---

## 🚀 快速开始：三分钟，开启您的 AI 之旅！

选择您最喜欢的冒险方式，让我们即刻出发！

### 方式一：Docker - 懒人福音 🐳 (强烈推荐)

这是最简单、最省心的方式。您不需要关心环境配置，只需几条命令。

**1. 准备工作**

*   安装 [Docker](https://www.docker.com/get-started) 和 [Docker Compose](https://docs.docker.com/compose/install/)。
*   克隆本项目：
    ```bash
    git clone https://github.com/lzA6/GLM-2api.git
    cd GLM-2api
    ```

**2. 创建您的“秘密指令”**

*   项目根目录下有一个 `.env.example` 文件。复制它并重命名为 `.env`：
    ```bash
    cp .env.example .env
    ```
*   打开 `.env` 文件，修改里面的配置。最重要的是设置您自己的 `AUTH_TOKEN`，这是您访问服务的密码。
    ```env
    # 客户端认证密钥（您自定义的 API 密钥，用于客户端访问本服务）
    AUTH_TOKEN=sk-your-secret-key-123456

    # Z.ai 备用访问令牌,可以放入到tokens.txt文件中
    # 注意：这是用于访问 Z.ai 服务的令牌，不是客户端认证密钥
    BACKUP_TOKEN=your_z_ai_token_here
    ```
*   (可选) 如果您有多个 Z.AI 令牌，可以在项目根目录创建一个 `tokens.txt` 文件，每行放一个令牌。`token_manager` 会自动加载它们。

**3. 启动帝国！**

*   在项目根目录，运行：
    ```bash
    docker-compose up -d
    ```
    这条命令会启动一个 Nginx 负载均衡器和两个 API 服务实例。您的“克隆军团”已经准备就绪！

**4. 验证**

*   您的服务现在运行在 `http://localhost:8084`。您可以像使用 OpenAI API 一样调用它了！

### 方式二：Replit - 云端 IDE 的魔法 ✨

无需本地环境，直接在浏览器中运行！

1.  点击下面的按钮，一键 Fork 到您的 Replit 账号：
    [![Run on Replit](https://replit.com/badge/github/lzA6/GLM-2api)](https://replit.com/github/lzA6/GLM-2api)
2.  在 Replit 的 `Secrets` 面板中，添加您的环境变量，例如 `AUTH_TOKEN` 和 `BACKUP_TOKEN`。
3.  点击 "Run" 按钮。Replit 会自动安装依赖并启动服务。
4.  您的 API 端点就是 Replit 为您生成的公开 URL。

### 方式三：本地部署 - 传统手艺人的选择 👨‍💻

如果您想完全掌控一切，可以手动在本地运行。

1.  **环境准备**：确保您已安装 Python 3.11+。
2.  **克隆项目**：
    ```bash
    git clone https://github.com/lzA6/GLM-2api.git
    cd GLM-2api
    ```
3.  **安装依赖**：
    ```bash
    pip install -r requirements.txt
    ```
4.  **配置**：同样，复制 `.env.example` 为 `.env` 并修改内容。
5.  **启动服务**：
    ```bash
    python main.py
    ```
6.  服务将运行在 `http://localhost:8080`。

---

## ⚙️ 配置详解：您的专属控制面板

通过 `.env` 文件，您可以精细地调整服务的行为。

| 变量名 | 作用 | 默认值 | 建议 |
| :--- | :--- | :--- | :--- |
| `API_ENDPOINT` | Z.AI 的 API 地址 | `https://chat.z.ai/api/chat/completions` | 一般无需修改 |
| `AUTH_TOKEN` | 访问本服务的密码 | `sk-your-api-key` | **务必修改为你自己的强密码！** |
| `SKIP_AUTH_TOKEN` | 是否跳过密码验证 | `false` | 仅供本地开发调试使用，**生产环境请设为 `false`** |
| `BACKUP_TOKEN` | Z.AI 的访问令牌 | (一个示例令牌) | 填入您自己的 Z.AI 令牌，或使用 `tokens.txt` |
| `LISTEN_PORT` | 服务监听的端口 | `8080` | 如果端口冲突可以修改 |
| `DEBUG_LOGGING` | 是否开启详细日志 | `false` | 调试问题时开启，平时关闭以提高性能 |
| `THINKING_PROCESSING` | 思考过程的处理方式 | `think` | `think` 兼容性最好，`strip` 最干净 |
| `ANONYMOUS_MODE` | 是否使用匿名模式 | `false` | 推荐设为 `true`，自动获取临时令牌，避免账号关联 |
| `TOOL_SUPPORT` | 是否开启工具调用 | `true` | 如果您不需要 Function Calling，可以关闭 |
| `HTTP_PROXY` / `HTTPS_PROXY` | HTTP/S 代理 | (无) | 如果您需要通过代理访问 Z.AI，请配置 |

---

## 🎯 使用示例：见证奇迹的时刻

现在，让我们用一个简单的 Python 脚本来调用我们的 API，并让模型查询天气。

```python
import requests
import json

# 您的 API 服务地址和密钥
API_BASE_URL = "http://localhost:8084"  # 如果使用 Docker Compose，端口是 8084
API_KEY = "sk-your-secret-key-123456"  # 替换为您在 .env 中设置的 AUTH_TOKEN

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

# 定义一个天气查询工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取一个城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称, e.g. 北京",
                    },
                },
                "required": ["city"],
            },
        }
    }
]

# 用户的请求
messages = [
    {"role": "user", "content": "今天上海的天气怎么样？"}
]

# 构建请求体
data = {
    "model": "GLM-4.5",  # 您可以根据需要选择支持的模型
    "messages": messages,
    "tools": tools,
    "tool_choice": "auto",  # 让模型自己决定是否使用工具
}

# 发送请求
try:
    response = requests.post(
        f"{API_BASE_URL}/v1/chat/completions",
        headers=headers,
        json=data
    )
    response.raise_for_status()  # 如果请求失败，则抛出异常

    # 解析响应
    result = response.json()
    message = result["choices"]["message"]

    if message.get("tool_calls"):
        print("🤖 模型决定调用工具：")
        tool_call = message["tool_calls"]
        function_name = tool_call["function"]["name"]
        arguments = json.loads(tool_call["function"]["arguments"])
        print(f"   - 函数名: {function_name}")
        print(f"   - 参数: {arguments}")
    else:
        print("🤖 模型直接回答：")
        print(message["content"])

except requests.exceptions.RequestException as e:
    print(f"请求出错了: {e}")

```

---

## 🧐 项目深度解析

### 👍 优点 (Pros)

1.  **无缝集成**：最大的优点！它让大量现有的、基于 OpenAI API 开发的生态工具、应用、客户端都能立刻使用 GLM 模型，学习成本几乎为零。
2.  **功能完整**：不仅支持基础的对话，还实现了流式响应、工具调用等高级功能，体验非常接近原生 OpenAI API。
3.  **稳定可靠**：内置的智能令牌池和重试机制，大大增强了服务的健壮性，能有效应对单个令牌失效或网络不稳定的情况。
4.  **高性能**：采用现代化的 Python Web 框架 FastAPI 和高性能的 ASGI 服务器 Granian，保证了 API 的高吞吐和低延迟。
5.  **易于扩展**：代码结构清晰，模块化设计（如 `transformer`, `token_manager`），方便未来添加对其他模型的支持，或者修改转换逻辑。

### 👎 缺点 (Cons)

1.  **依赖于第三方**：本项目强依赖于 Z.AI 的非公开 API。如果 Z.AI 官方对 API 进行修改、限制或关闭，本项目可能会失效。这是一种“寄生”关系，存在不确定性。
2.  **潜在的合规风险**：模拟和转换第三方 API 可能涉及服务条款（ToS）问题。请用户自行评估在自己的使用场景下是否合规。**本项目仅供学习和技术研究，请勿用于商业或非法用途。**
3.  **维护成本**：由于依赖于随时可能变化的非官方接口，需要持续关注上游变化并及时更新代码以保持可用性。

### 适用场景

*   **个人开发者**：希望在自己的小项目或原型中使用 GLM 模型，但又不想重写大量代码。
*   **学习与研究**：深入理解 API 转换、SSE 流处理、Function Calling 实现原理的绝佳案例。
*   **内部工具集成**：企业内部有许多基于 OpenAI API 的工具，希望快速切换到 GLM 模型进行测试或内部使用。
*   **AI 应用爱好者**：希望在各种第三方客户端（如 NextChat, LobeChat）中体验 GLM 模型。

---

## 展望未来：星辰大海的征途 🌌

这个项目目前已经完成了核心的桥接功能，但我们的征途才刚刚开始。未来，我们可以探索更多激动人心的可能性：

*   **支持更多模型后端**：除了 Z.AI，我们还可以编写更多的 `transformer`，来支持其他优秀的国产大模型，让 GLM-2api 成为一个真正的“万能转换器”。
*   **可视化管理面板**：开发一个简单的 Web UI，可以实时查看令牌池状态、请求日志、统计数据，甚至在线热重载配置。
*   **智能缓存系统**：对于一些重复性的请求，引入缓存机制（如 Redis），可以降低成本并提高响应速度。
*   **更精细的负载均衡策略**：除了轮询，还可以实现基于响应时间、失败率的更智能的负载均衡算法。
*   **插件化架构**：将核心逻辑与模型适配层分离，允许社区开发者轻松编写插件来支持新的模型或功能。

---

## ❤️ 贡献：众人拾柴火焰高

我们相信开源的力量，也相信每一个人的智慧。如果您对这个项目有任何想法、建议或发现了 Bug，都热烈欢迎您：

1.  **提交 Issue**：有任何问题或新功能建议，请不要犹豫，在 [GitHub Issues](https://github.com/lzA6/GLM-2api/issues) 中告诉我们。
2.  **发起 Pull Request**：如果您修复了 Bug 或实现了新功能，请大胆地提交 PR！我们非常乐意与您一起完善这个项目。

让我们一起，把这座桥建得更宽、更长、更坚固！

## 📜 开源协议

本项目采用 **Apache 2.0** 开源协议。

这意味着您可以自由地使用、修改和分发本软件，无论是商业还是非商业用途，但需要遵守协议中的相关条款。

```text
Copyright 2025 lzA6

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

---

**最后，感谢您的阅读。愿代码与您同在，愿探索精神永不熄灭！**
