from typing import Any

from app.core.config import Settings


class ModelConfigurationError(RuntimeError):
    pass


def create_chat_model(settings: Settings) -> Any:
    if not settings.model_configured:
        raise ModelConfigurationError("聊天模型尚未配置，请填写 .env 中的 MODEL_* 配置")

    if settings.model_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.model_name,
            base_url=settings.model_base_url or None,
            temperature=settings.model_temperature,
        )

    if settings.model_provider == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=settings.model_name,
            api_key=settings.model_api_key,
            api_base=settings.model_base_url or None,
            temperature=settings.model_temperature,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.model_api_key,
        base_url=settings.model_base_url or None,
        temperature=settings.model_temperature,
    )


def create_embedding_model(settings: Settings) -> Any:
    if not settings.embedding_configured:
        raise ModelConfigurationError("嵌入模型尚未配置，请填写 .env 中的 EMBEDDING_* 配置")

    if settings.embedding_provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.embedding_base_url or None,
        )

    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url or None,
        dimensions=settings.embedding_dimension,
        # Bailian's OpenAI-compatible endpoint accepts raw strings, not token arrays.
        check_embedding_ctx_length=False,
    )
