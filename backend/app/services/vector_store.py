"""向量库封装：Chroma + 本地 BGE / OpenAI 兼容 Embedding。"""

import logging
import os
import re

from app.config import settings

logger = logging.getLogger(__name__)

_embedder = None
_embedder_error: str | None = None
_chroma_client = None
_collection = None


def _provider() -> str:
    """解析 Embedding 提供方；配置了 Key 时默认走 OpenAI 兼容接口。"""
    provider = settings.EMBEDDING_PROVIDER.strip().lower()
    if provider in {"local", "openai"}:
        return provider
    return "openai" if settings.EMBEDDING_KEY else "local"


def _collection_name() -> str:
    """按 Embedding 模型区分集合，避免模型切换后维度不一致。"""
    raw = re.sub(r"[^a-zA-Z0-9]+", "_", settings.EMBEDDING_MODEL).strip("_").lower()
    return f"knowledge_{raw[:40]}" if raw else "knowledge_default"


def _get_collection():
    """延迟初始化 Chroma，避免应用启动时加载重型依赖。"""
    global _chroma_client, _collection
    if _collection is None:
        import chromadb

        os.makedirs(settings.CHROMA_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DIR)
        _collection = _chroma_client.get_or_create_collection(
            name=_collection_name(),
            configuration={"hnsw": {"space": "cosine"}},
        )
    return _collection


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化：默认本地 BGE，可切换 OpenAI 兼容接口。"""
    if not texts:
        return []

    if _provider() == "openai":
        if not settings.EMBEDDING_KEY:
            raise RuntimeError("未配置 EMBEDDING_KEY，无法调用远程 Embedding")
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.EMBEDDING_KEY,
            base_url=settings.EMBEDDING_BASE_URL or None,
            timeout=settings.LLM_TIMEOUT,
        )
        vectors: list[list[float]] = []
        # 远程接口限制单次输入数量，按批请求并保持顺序
        batch_size = 16
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            response = client.embeddings.create(
                model=settings.EMBEDDING_MODEL, input=batch
            )
            vectors.extend([item.embedding for item in response.data])
        return vectors

    global _embedder, _embedder_error
    if _embedder_error:
        raise RuntimeError(
            "本地 Embedding 初始化失败（无法访问 HuggingFace）。"
            "请将 EMBEDDING_PROVIDER 设为 openai，并配置 EMBEDDING_KEY 与 EMBEDDING_BASE_URL。"
        ) from None

    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer

            _embedder = SentenceTransformer(settings.EMBEDDING_MODEL)
        except Exception as exc:
            _embedder_error = str(exc)
            logger.exception("本地 Embedding 初始化失败")
            raise RuntimeError(
                "本地 Embedding 初始化失败（无法访问 HuggingFace）。"
                "请将 EMBEDDING_PROVIDER 设为 openai，并配置 EMBEDDING_KEY 与 EMBEDDING_BASE_URL。"
            ) from exc

    vectors = _embedder.encode(
        texts,
        normalize_embeddings=True,
        batch_size=8,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in vectors]


def upsert_chunks(
    document_id: int,
    document_name: str,
    chunks: list[dict],
    vectors: list[list[float]],
) -> list[str]:
    """写入文档切片向量，返回向量库记录 ID。"""
    collection = _get_collection()
    ids = [f"doc{document_id}_chunk{index}" for index in range(len(chunks))]
    metadatas = [
        {
            "document_id": document_id,
            "document_name": document_name,
            "chunk_index": index,
            "page_no": chunk.get("page_no") or -1,
        }
        for index, chunk in enumerate(chunks)
    ]
    collection.upsert(
        ids=ids,
        documents=[chunk["content"] for chunk in chunks],
        embeddings=vectors,
        metadatas=metadatas,
    )
    return ids


def delete_document(document_id: int) -> None:
    """删除某文档的全部向量。"""
    try:
        collection = _get_collection()
        collection.delete(where={"document_id": document_id})
    except Exception:  # 向量库异常不应阻断数据库清理
        logger.warning("删除向量失败：document_id=%s", document_id, exc_info=True)


def search(query: str, top_k: int = 5, min_score: float = 0.2) -> list[dict]:
    """相似度检索，返回切片与得分。"""
    collection = _get_collection()
    count = collection.count()
    if count == 0:
        return []

    query_vector = embed_texts([query])[0]
    result = collection.query(
        query_embeddings=[query_vector],
        n_results=min(max(top_k, 1), count),
        include=["documents", "metadatas", "distances"],
    )

    documents = (result.get("documents") or [[]])[0]
    metadatas = (result.get("metadatas") or [[]])[0]
    distances = (result.get("distances") or [[]])[0]

    items: list[dict] = []
    for content, metadata, distance in zip(documents, metadatas, distances):
        score = 1 - float(distance)
        if score < min_score:
            continue
        page_no = metadata.get("page_no")
        items.append(
            {
                "document_id": int(metadata["document_id"]),
                "document_name": metadata.get("document_name", ""),
                "chunk_index": int(metadata.get("chunk_index", 0)),
                "content": content,
                "score": round(score, 4),
                "page_no": int(page_no) if page_no and int(page_no) > 0 else None,
            }
        )
    return items
