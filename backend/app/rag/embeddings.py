from langchain_openai import OpenAIEmbeddings

from app.core.config import settings

_embeddings: OpenAIEmbeddings | None = None


def get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key or None,
        )
    return _embeddings


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await get_embeddings().aembed_documents(texts)


async def embed_query(query: str) -> list[float]:
    return await get_embeddings().aembed_query(query)
