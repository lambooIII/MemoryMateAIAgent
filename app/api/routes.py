import json
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse

from app.models.factory import ModelConfigurationError
from app.schemas.chat import ChatRequest, ChatResponse, StatusResponse


router = APIRouter(prefix="/api")


def _agent_service(request: Request):
    service = getattr(request.app.state, "agent_service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail="聊天模型尚未配置，请根据 .env.example 填写 MODEL_* 配置后重启服务",
        )
    return service


@router.get("/knowledge/notes")
def list_knowledge_notes(subject_id: str, request: Request) -> dict:
    notes = request.app.state.rag_service.list_memory_notes(subject_id)
    return {"subject_id": subject_id, "notes": notes, "count": len(notes)}


@router.get("/knowledge/graph")
def knowledge_graph(request: Request, subject_id: str = "all") -> dict:
    return request.app.state.rag_service.graph(subject_id)


@router.delete("/knowledge/subjects/{subject_id}")
async def delete_knowledge_subject(subject_id: str, request: Request) -> dict[str, int | str]:
    try:
        removed_chunks = await run_in_threadpool(request.app.state.rag_service.delete_subject, subject_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"删除对象资料失败：{exc}") from exc
    return {"subject_id": subject_id, "removed_chunks": removed_chunks}


@router.get("/status", response_model=StatusResponse)
def status(request: Request) -> StatusResponse:
    settings = request.app.state.settings
    rag_service = request.app.state.rag_service
    return StatusResponse(
        status="ready" if settings.model_configured else "configuration_required",
        configured=settings.model_configured,
        capabilities={
            "model_provider": settings.model_provider,
            "model_name": settings.model_name or "未配置",
            "short_term_memory": settings.short_term_memory_backend,
            "long_term_memory": settings.long_term_memory_backend,
            "vector_store": settings.vector_store_backend,
            "rag_enabled": settings.enable_rag,
            "embedding_configured": settings.embedding_configured,
            "knowledge_chunks": rag_service.count(),
            "web_search_enabled": settings.enable_web_search,
            "summarization_enabled": settings.enable_summarization,
            "pii_protection_enabled": settings.enable_pii_protection,
        },
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    service = _agent_service(request)
    try:
        answer = await run_in_threadpool(
            service.invoke,
            payload.message,
            payload.thread_id,
            payload.user_id,
            payload.subject_id,
        )
    except ModelConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent 调用失败：{exc}") from exc
    return ChatResponse(
        answer=answer,
        thread_id=payload.thread_id,
        user_id=payload.user_id,
        subject_id=payload.subject_id,
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    service = _agent_service(request)

    async def events():
        try:
            async for token in service.stream(
                payload.message,
                payload.thread_id,
                payload.user_id,
                payload.subject_id,
            ):
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error = {"type": "error", "content": str(exc)}
            yield f"data: {json.dumps(error, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(thread_id: str, request: Request) -> None:
    service = _agent_service(request)
    try:
        await run_in_threadpool(service.clear_thread, thread_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清空会话失败：{exc}") from exc


@router.post("/threads/{thread_id}/reset", status_code=204)
async def reset_thread_compatibility(thread_id: str, request: Request) -> None:
    """Keep the course-style reset endpoint while the web UI uses DELETE."""
    await delete_thread(thread_id, request)


@router.post("/knowledge/ingest")
async def ingest_knowledge(
    request: Request,
    files: list[UploadFile] = File(default=[]),
    subject_id: str = Form(default="general"),
) -> dict[str, int]:
    rag_service = request.app.state.rag_service
    settings = request.app.state.settings
    try:
        if files:
            subject_directory = rag_service.subject_directory(subject_id)
            paths: list[Path] = []
            for file in files:
                suffix = Path(file.filename or "").suffix.lower()
                if suffix not in {".txt", ".md"}:
                    raise HTTPException(
                        status_code=400,
                        detail="MVP 仅支持 UTF-8 编码的 .txt 和 .md 文件",
                    )
                safe_name = Path(file.filename or f"upload{suffix}").name
                target = subject_directory / safe_name
                content = await file.read()
                try:
                    target.write_text(content.decode("utf-8"), encoding="utf-8")
                except UnicodeDecodeError as exc:
                    raise HTTPException(status_code=400, detail="文件必须使用 UTF-8 编码") from exc
                paths.append(target)
            count = await run_in_threadpool(rag_service.ingest_paths, paths, subject_id)
        else:
            count = await run_in_threadpool(rag_service.ingest_directory, None, subject_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"知识库导入失败：{exc}") from exc
    return {"ingested_chunks": count, "total_chunks": rag_service.count()}


@router.post("/knowledge/upload")
async def upload_knowledge(request: Request, file: UploadFile = File(...)) -> dict[str, int | str]:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".txt", ".md"}:
        raise HTTPException(status_code=400, detail="MVP 仅支持 UTF-8 编码的 .txt 和 .md 文件")
    settings = request.app.state.settings
    settings.knowledge_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or f"upload{suffix}").name
    target = settings.knowledge_dir / safe_name
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="文件必须使用 UTF-8 编码") from exc
    target.write_text(text, encoding="utf-8")
    try:
        count = await run_in_threadpool(request.app.state.rag_service.ingest_paths, [target])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文件向量化失败：{exc}") from exc
    return {"filename": safe_name, "ingested_chunks": count}
