import json

from langchain_core.tools import tool
from langgraph.prebuilt import ToolRuntime

from app.schemas.chat import UserProfile


@tool(args_schema=UserProfile)
def save_user_profile(
    name: str | None = None,
    occupation: str | None = None,
    preferences: list[str] | None = None,
    runtime: ToolRuntime = None,
) -> str:
    """当用户明确提供姓名、职业或个人偏好时，将信息保存为跨会话长期记忆。"""
    if runtime is None:
        return "无法访问记忆运行时"
    user_id = runtime.state.get("user_id", "anonymous")
    namespace = ("users", user_id, "profile")
    existing = runtime.store.get(namespace, "profile")
    profile = dict(existing.value) if existing else {}
    updates = {
        "name": name,
        "occupation": occupation,
        "preferences": preferences or [],
    }
    profile.update({key: value for key, value in updates.items() if value not in (None, [])})
    runtime.store.put(namespace, "profile", profile)
    return "用户资料已保存"


@tool
def get_user_profile(runtime: ToolRuntime) -> str:
    """在需要个性化回答或用户询问自身信息时读取长期记忆。"""
    user_id = runtime.state.get("user_id", "anonymous")
    item = runtime.store.get(("users", user_id, "profile"), "profile")
    if item is None:
        return "尚未保存该用户的资料"
    return json.dumps(item.value, ensure_ascii=False)


def get_memory_tools() -> list:
    return [save_user_profile, get_user_profile]

