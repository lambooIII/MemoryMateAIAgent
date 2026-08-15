import json

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from app.schemas.chat import UserProfile


@tool(args_schema=UserProfile)
def save_partner_profile(
    partner_name: str | None = None,
    birthday: str | None = None,
    occupation: str | None = None,
    preferences: list[str] | None = None,
    dislikes: list[str] | None = None,
    important_dates: dict[str, str] | None = None,
    runtime: ToolRuntime = None,
) -> str:
    """当用户明确提供对象资料、喜好、雷区或重要日期时保存为跨会话长期记忆。"""
    if runtime is None:
        return "无法访问记忆运行时"
    user_id = runtime.state.get("user_id", "anonymous")
    namespace = ("users", user_id, "profile")
    existing = runtime.store.get(namespace, "profile")
    profile = dict(existing.value) if existing else {}
    updates = {
        "partner_name": partner_name,
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
def get_partner_profile(runtime: ToolRuntime) -> str:
    """查询恋爱对象资料、喜好、雷区和重要日期。"""
    user_id = runtime.state.get("user_id", "anonymous")
    item = runtime.store.get(("users", user_id, "profile"), "profile")
    if item is None:
        return "尚未保存该用户的资料"
    return json.dumps(item.value, ensure_ascii=False)


def get_memory_tools() -> list:
    return [save_partner_profile, get_partner_profile]
