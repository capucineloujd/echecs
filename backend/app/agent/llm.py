import logging

from langchain_core.language_models import BaseChatModel

from app.config import Settings


logger = logging.getLogger(__name__)


def build_chat_model(settings: Settings) -> BaseChatModel | None:
    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=settings.llm_temperature,
            # contexte par défaut d'Ollama trop petit
            num_ctx=settings.ollama_num_ctx,
            reasoning=settings.ollama_reasoning,
            client_kwargs={"timeout": settings.llm_timeout_seconds},
        )

    if settings.llm_provider == "mistral":
        if not settings.mistral_api_key:
            logger.warning("Coach désactivé : MISTRAL_API_KEY absente")
            return None
        from langchain_mistralai import ChatMistralAI

        return ChatMistralAI(
            model=settings.mistral_model,
            api_key=settings.mistral_api_key,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    raise ValueError(f"LLM_PROVIDER inconnu : {settings.llm_provider!r} (ollama ou mistral)")
