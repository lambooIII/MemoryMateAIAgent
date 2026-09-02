# MemoryMate AI

这是一个根据 LangChain 1.2 课程代码整理的教学型私人关系记忆助手。它以人物姓名作为唯一标识，分别管理家人、恋人、朋友等人物资料，检索私人备忘录、记住用户确认过的关系、昵称和偏好，并在需要时调用实时工具。恋爱助手是其中的一个使用场景。

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
- SQLite GraphRAG、实体关系抽取、聚合查询和最多三跳路径检索
- 内存向量库 / Milvus 切换
- LangSmith 可选追踪
- FastAPI、SSE 和简单网页工作台

`knowledge/` 默认保持为空，用户可以在网页中上传 `.txt`/`.md` 人物笔记，也可以在聊天中补充姓名、关系、昵称、生日、喜好、雷区和重要日期。前端通过 `subject_id` 指定人物姓名，长期记忆按 `user_id + subject_id` 隔离；“室友”“妈妈”等关系不会作为主键。聊天提取到的新信息应先由用户确认，再写入长期记忆和 RAG 索引。

## 项目结构

```text
app/
├─ agents/       Agent 创建、Prompt 和调用
├─ api/          FastAPI 接口
├─ core/         配置与日志
├─ graph/        SQLite 图谱、结构化抽取、聚合与多跳查询
├─ memory/       长短期记忆后端工厂
├─ models/       ChatModel 与 Embedding 工厂
├─ rag/          文档切分、向量仓储和检索
├─ schemas/      Pydantic 数据结构
└─ tools/        Agent 工具
knowledge/       本地知识文件
data/            本地 SQLite 知识图谱（运行时生成）
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

如果已经激活 `langchain1.2` 环境，也可以直接运行：

```powershell
conda activate langchain1.2
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

浏览器打开 `http://127.0.0.1:8000`。接口文档位于 `http://127.0.0.1:8000/docs`。

学习后端流程时，也可以只访问 `http://127.0.0.1:8000/docs`，用 Swagger 调用接口，不需要先理解网页代码。

没有填写模型密钥时服务仍能启动，状态页会提示“等待配置”，聊天接口不会发送任何外部请求。

## 3. 体验 RAG 流程

将 UTF-8 编码的 `.txt` 或 `.md` 关系笔记放入 `knowledge`，然后在工作台点击“保存到备忘录”，或者执行：

```powershell
conda run --no-capture-output -n langchain1.2 python scripts/ingest.py
```

数据流程如下：

```text
文档 -> RecursiveCharacterTextSplitter -> Embedding
     -> 内存/Milvus -> retrieve_knowledge 工具 -> Agent 回答
     -> 实体关系抽取 -> SQLite 图谱 -> 聚合/多跳工具 -> Agent 回答
```

内存向量库在进程重启后会清空，但默认启用 `AUTO_INGEST_LOCAL_KNOWLEDGE=true`。服务或电脑重启后会扫描 `knowledge/<subject_id>/`，自动调用 Embedding 并重建向量索引，不需要重新上传。原始 Markdown 文件是持久化数据源，向量只是可以随时重建的检索索引。

### GraphRAG 初版

本地图谱默认开启，不需要安装 Neo4j 或其他数据库服务：

```dotenv
ENABLE_KNOWLEDGE_GRAPH=true
ENABLE_GRAPH_EXTRACTION=true
GRAPH_DATABASE_PATH=data/knowledge_graph.db
GRAPH_MAX_DEPTH=3
```

上传文档时，系统会在原有向量入库之外抽取人物、部门、组织、地点等实体，以及“任职于”“负责人”“位于”等关系。每条关系均保存来源文件和原文证据，结果持久化到 SQLite。文件内容未变化时不会重复抽取；文件更新后会替换该文档对应的旧关系。

Agent 新增三类图谱工具：

- `query_entity_relations`：查询实体的一跳关系。
- `aggregate_graph_entities`：对关系目标执行去重计数，例如“财务部有多少人”。
- `find_relation_paths`：查询两个实体之间最多三跳的关系路径。

可上传以下格式的多份人物文档进行基础演示：

```markdown
- 姓名：张三
- 所在部门：财务部
```

然后询问“财务部有多少人”。系统会对指向财务部的 `person` 实体去重统计，并返回名单和原文证据。复杂自然语言关系由聊天模型结构化抽取；姓名、部门、单位和地址等显式字段另有规则抽取兜底。

当前版本是本地 GraphRAG 初版：支持一跳关系、聚合统计、限制深度的路径搜索和图谱可视化，尚未使用图数据库查询语言，也不包含社区发现等高级 GraphRAG 算法。

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

基于 LangChain 与 LangGraph 构建私人记忆型 AI Agent，通过 ReAct 式 Tool Calling 动态路由向量 RAG、SQLite 知识图谱和 Tavily 联网搜索；支持从上传文档中抽取实体关系、保留来源证据，并通过图谱聚合和限制深度的多跳路径检索回答跨文档关系问题。使用 FastAPI 与 SSE 提供多会话流式服务，支持实体归并、关系图谱展示以及 PostgreSQL、Milvus 可切换存储方案。
