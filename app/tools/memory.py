import json

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from app.schemas.chat import SubjectProfile


@tool(args_schema=SubjectProfile)
def save_subject_profile(
    relation: str | None = None,
    name: str | None = None,
    birthday: str | None = None,
    occupation: str | None = None,
    preferences: list[str] | None = None,
    dislikes: list[str] | None = None,
    important_dates: dict[str, str] | None = None,
    runtime: ToolRuntime = None,
) -> str:
    """当用户明确提供关系对象资料、喜好、雷区或重要日期时保存为跨会话长期记忆。"""
    if runtime is None:
        return "无法访问记忆运行时"
    user_id = runtime.state.get("user_id", "anonymous")
    subject_id = runtime.state.get("subject_id", "partner")
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
    }
    profile.update({key: value for key, value in updates.items() if value not in (None, [])})
    runtime.store.put(namespace, "profile", profile)
    return "用户资料已保存"


@tool
def get_subject_profile(runtime: ToolRuntime) -> str:
    """查询当前关系对象的资料、喜好、雷区和重要日期。"""
    user_id = runtime.state.get("user_id", "anonymous")
    subject_id = runtime.state.get("subject_id", "partner")
    item = runtime.store.get(("users", user_id, "subjects", subject_id), "profile")
    if item is None:
        return "尚未保存该用户的资料"
    return json.dumps(item.value, ensure_ascii=False)


def get_memory_tools() -> list:
    return [save_subject_profile, get_subject_profile]
