"""Factory functions for the Gemini chat model and embedding model.

Every agent gets its model from here, so switching model (or switching from
the AI Studio API key to Vertex AI on GCP) is a one-line config change.
"""
import os
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

from .config import settings


class LLMNotConfigured(RuntimeError):
    pass


def _auth_kwargs() -> dict:
    if settings.use_vertexai:
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.gcp_project)  # used by google-auth for quota
        return {"vertexai": True, "project": settings.gcp_project, "location": settings.gcp_location}
    if not settings.google_api_key:
        raise LLMNotConfigured("GOOGLE_API_KEY is not set. Add it to your .env file.")
    return {"api_key": settings.google_api_key}


@lru_cache
def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    # temperature 0 = as deterministic as possible; we want consistent routing and banking answers.
    return ChatGoogleGenerativeAI(
        model=settings.gemini_model, temperature=temperature, retries=2, **_auth_kwargs()
    )


@lru_cache
def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(model=settings.gemini_embedding_model, **_auth_kwargs())
