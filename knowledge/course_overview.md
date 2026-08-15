# LangChain 课程知识概要

本项目综合演示模型调用、消息与提示词、工具调用、结构化输出、Agent、中间件、短期记忆、长期记忆和 RAG。

短期记忆通过 checkpointer 按 thread_id 保存同一会话的状态。内存实现适合本地体验，PostgreSQL 实现适合需要跨进程和重启持久化的环境。

长期记忆通过 store 按 user_id 保存用户画像和偏好，可以跨多个 thread_id 读取。PostgresSaver 和 PostgresStore 可以使用同一个 PostgreSQL 数据库实例。

RAG 将文档切分为文本块，通过嵌入模型生成向量，再使用向量相似度检索相关内容。内存向量库适合快速体验，Milvus 适合持久化和大规模向量检索。

