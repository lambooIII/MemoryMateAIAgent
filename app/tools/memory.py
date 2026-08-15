import json
from datetime import datetime
from uuid import uuid4

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from app.schemas.chat import SubjectProfile


def _build_memory_content(data: dict) -> str:
    labels = {
        "relation": "关系",
        "name": "姓名",
        "birthday": "生日",
        "occupation": "职业或工作信息",
        "preferences": "喜欢",
        "dislikes": "不喜欢或需要避开",
        "important_dates": "重要日期",
        "summary": "补充摘要",
    }
    return "\n".join(
        f"- {labels[key]}：{json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value}"
        for key, value in data.items()
        if key in labels and value not in (None, [], {})
    )


def get_memory_tools(rag_service) -> list:
    @tool(args_schema=SubjectProfile)
    def save_subject_profile(
    relation: str | None = None,
    name: str | None = None,
    birthday: str | None = None,
    occupation: str | None = None,
    preferences: list[str] | None = None,
    dislikes: list[str] | None = None,
    important_dates: dict[str, str] | None = None,
    category: str = "general",
    summary: str | None = None,
    runtime: ToolRuntime = None,
) -> str:
        """仅在用户明确确认后，保存当前关系对象的重要信息并更新 RAG。"""
        if runtime is None:
            return "无法访问记忆运行时"
        user_id = runtime.state.get("user_id", "anonymous")
        subject_id = runtime.state.get("subject_id", "all")
        if subject_id in {"", "all", "全部"}:
            subject_id = (relation or name or "").strip()
            if not subject_id:
                return "当前知识范围是全部对象，无法判断资料属于谁。请先选择或新增对象后再保存。"
        namespace = ("users", user_id, "subjects", subject_id)
        existing = runtime.store.get(namespace, "profile")
        profile = dict(existing.value) if existing else {}
        updates = {
            "relation": relation,
            "name": name,
            "birthday": birthday,
            "occupation": occupation,
            "preferences": preferences or [],
            "dislikes": dislikes or [],
            "important_dates": important_dates or {},
            "summary": summary,
        }
        for key, value in updates.items():
            if value in (None, [], {}):
                continue
            if isinstance(value, list):
                profile[key] = list(dict.fromkeys([*profile.get(key, []), *value]))
            elif isinstance(value, dict):
                profile[key] = {**profile.get(key, {}), **value}
            else:
                profile[key] = value
        runtime.store.put(namespace, "profile", profile)

        saved_at = datetime.now().astimezone().isoformat(timespec="seconds")
        memory_value = {**updates, "category": category, "saved_at": saved_at}
        runtime.store.put((*namespace, "memories"), uuid4().hex, memory_value)
        content = _build_memory_content(memory_value)
        if not content:
            return "没有可保存的重要信息"
        title = f"{subject_id}的{category}记录"
        try:
            path, chunk_count = rag_service.save_memory_note(
                subject_id=subject_id,
                title=title,
                content=content,
                category=category,
            )
            return f"已保存长期记忆和 RAG 笔记：{path.name}，生成 {chunk_count} 个文本块"
        except Exception as exc:
            return f"长期记忆已保存，但本地笔记或 RAG 更新失败：{exc}"


    @tool
    def get_subject_profile(runtime: ToolRuntime) -> str:
        """查询当前关系对象的资料、喜好、雷区和重要日期。"""
        user_id = runtime.state.get("user_id", "anonymous")
        subject_id = runtime.state.get("subject_id", "all")
        if subject_id in {"", "all", "全部"}:
            return "当前知识范围是全部对象，请选择具体对象后查询结构化档案。"
        item = runtime.store.get(("users", user_id, "subjects", subject_id), "profile")
        if item is None:
            return "尚未保存当前关系对象的资料"
        return json.dumps(item.value, ensure_ascii=False)

    @tool
    def merge_subject(
        source_subject_id: str,
        target_subject_id: str,
        runtime: ToolRuntime,
    ) -> str:
        """仅在用户确认两个对象是同一人后，将来源对象资料合并到目标对象并移除重复对象。"""
        user_id = runtime.state.get("user_id", "anonymous")
        source_namespace = ("users", user_id, "subjects", source_subject_id)
        target_namespace = ("users", user_id, "subjects", target_subject_id)
        source_item = runtime.store.get(source_namespace, "profile")
        target_item = runtime.store.get(target_namespace, "profile")
        source_profile = dict(source_item.value) if source_item else {}
        target_profile = dict(target_item.value) if target_item else {}
        try:
            chunk_count = rag_service.merge_subject(source_subject_id, target_subject_id)
        except Exception as exc:
            return f"对象合并失败：{exc}"
        for key, value in source_profile.items():
            if isinstance(value, list):
                target_profile[key] = list(dict.fromkeys([*target_profile.get(key, []), *value]))
            elif isinstance(value, dict):
                target_profile[key] = {**value, **target_profile.get(key, {})}
            elif key not in target_profile or target_profile[key] in (None, ""):
                target_profile[key] = value
        if target_profile:
            runtime.store.put(target_namespace, "profile", target_profile)
        delete = getattr(runtime.store, "delete", None)
        if source_item is not None and delete is not None:
            delete(source_namespace, "profile")
        return f"已将{source_subject_id}合并到{target_subject_id}，更新了 {chunk_count} 个知识片段"

    return [save_subject_profile, get_subject_profile, merge_subject]
