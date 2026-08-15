# Course Agent Workspace

这是一个根据 LangChain 1.2 课程代码整理的教学型 AI Agent + RAG MVP。项目重点是完整走通模型、工具、Agent、中间件、记忆和知识库检索流程，并提供一个可以直接操作的网页工作台。

## 已覆盖的课程知识点

- `.env` 环境变量和多模型工厂
- Message、系统提示词和流式输出
- `@tool` 工具：安全计算、时间、RAG、长期记忆
- Pydantic 结构化参数 `UserProfile`
- `create_agent` 智能体
- `SummarizationMiddleware` 和 `PIIMiddleware` 可选中间件
- `InMemorySaver` / `PostgresSaver` 短期记忆
- `InMemoryStore` / `PostgresStore` 长期记忆
- 文档加载、递归切分、Embedding 和向量检索
- 内存向量库 / Milvus 切换
- LangSmith 可选追踪
- FastAPI、SSE 和简单网页工作台

## 项目结构

```text
app/
├─ agents/       Agent 创建、Prompt 和调用
├─ api/          FastAPI 接口
├─ core/         配置与日志
├─ memory/       长短期记忆后端工厂
├─ models/       ChatModel 与 Embedding 工厂
├─ rag/          文档切分、向量仓储和检索
├─ schemas/      Pydantic 数据结构
└─ tools/        Agent 工具
knowledge/       本地知识文件
scripts/         独立知识导入脚本
tests/           核心测试
web/             浏览器工作台
```

`web/` 是独立的原生 HTML/CSS/JavaScript 前端，只依赖 `/api` 接口和 SSE 数据格式。后端的核心 Agent、记忆和 RAG 模块不导入任何前端代码，因此你可以先运行和阅读 `app/`，再单独学习 `web/`；也可以把 `web/` 替换成 Vue、React 或其他客户端。

## 1. 配置环境

项目使用你已经安装好课程依赖的 Conda 环境 `langchain1.2`。

```powershell
Copy-Item .env.example .env
```

打开 `.env`，至少填写聊天模型：

```dotenv
MODEL_PROVIDER=openai_compatible
MODEL_NAME=你的模型名称
MODEL_API_KEY=你的API密钥
MODEL_BASE_URL=你的模型接口地址
```

RAG 还需要填写嵌入模型密钥：

```dotenv
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_MODEL=Pro/BAAI/bge-m3
EMBEDDING_API_KEY=你的API密钥
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_DIMENSION=1024
```

密钥只填写到 `.env`。该文件已经被 Git 忽略，不要把真实密钥写入 `.env.example` 或 Python 代码。

## 2. 启动项目

```powershell
.\run.ps1
```

也可以手动运行：

```powershell
conda run --no-capture-output -n langchain1.2 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

浏览器打开 `http://127.0.0.1:8000`。接口文档位于 `http://127.0.0.1:8000/docs`。

学习后端流程时，也可以只访问 `http://127.0.0.1:8000/docs`，用 Swagger 调用接口，不需要先理解网页代码。

没有填写模型密钥时服务仍能启动，状态页会提示“等待配置”，聊天接口不会发送任何外部请求。

## 3. 体验 RAG 流程

将 UTF-8 编码的 `.txt` 或 `.md` 文件放入 `knowledge`，然后在工作台点击“导入知识库”，或者执行：

```powershell
conda run --no-capture-output -n langchain1.2 python scripts/ingest.py
```

数据流程如下：

```text
文档 -> RecursiveCharacterTextSplitter -> Embedding
     -> 内存/Milvus -> retrieve_knowledge 工具 -> Agent 回答
```

内存向量库在进程重启后会清空，重启后重新导入即可。

## 4. 切换长短期记忆

默认不需要安装数据库：

```dotenv
SHORT_TERM_MEMORY_BACKEND=memory
LONG_TERM_MEMORY_BACKEND=memory
VECTOR_STORE_BACKEND=memory
```

安装 PostgreSQL 后，可以只切换其中一种，也可以同时切换：

```dotenv
SHORT_TERM_MEMORY_BACKEND=postgres
LONG_TERM_MEMORY_BACKEND=postgres
POSTGRES_URI=postgresql://用户名:密码@主机:5432/数据库名
```

短期记忆由 `thread_id` 隔离，负责同一会话的上下文；长期记忆由 `user_id` 隔离，负责跨会话保存用户画像。`PostgresSaver` 和 `PostgresStore` 可以共用同一个 PostgreSQL 数据库。

## 5. 切换 Milvus

```dotenv
VECTOR_STORE_BACKEND=milvus
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=
MILVUS_DATABASE=course_agent
MILVUS_COLLECTION=knowledge_chunks
```

项目启动时只会按需创建数据库和 collection，不会自动删除已有数据。Embedding 模型的实际维度必须等于 `EMBEDDING_DIMENSION`。

## 6. 可选能力

```dotenv
ENABLE_WEB_SEARCH=false
TAVILY_API_KEY=

ENABLE_SUMMARIZATION=false
SUMMARY_TRIGGER_MESSAGES=12
SUMMARY_KEEP_MESSAGES=6

ENABLE_PII_PROTECTION=false
LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
```

这些功能默认关闭，便于先看清核心流程。需要观察长对话摘要、隐私处理或 LangSmith 追踪时再逐项开启。

## 7. 运行测试

```powershell
conda run --no-capture-output -n langchain1.2 python -m pytest -q
```

## 简历描述参考

基于 LangChain 1.2 与 FastAPI 开发可配置的 AI Agent + RAG 知识助手，整合工具调用、SSE 流式响应、长短期记忆、Pydantic 结构化参数及中间件机制；通过工厂模式支持内存/PostgreSQL 记忆和内存/Milvus 向量检索切换，实现文档切分、Embedding、语义检索与来源引用的完整知识库问答链路。
