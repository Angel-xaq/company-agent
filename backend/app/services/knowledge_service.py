import logging
import re
from pathlib import Path
from uuid import uuid4

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.common.exceptions import BusinessException
from app.common.response import PageResponse
from app.config import settings
from app.core.constants import (
    DOC_FAILED,
    DOC_PENDING,
    DOC_PROCESSING,
    DOC_READY,
    PERM_KB_MANAGE,
)
from app.database import SessionLocal
from app.dependencies.auth import has_permission
from app.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.models.user import User
from app.schemas.knowledge import KnowledgeDocumentResponse
from app.services import vector_store

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "docx", "md", "txt"}
ALLOWED_CATEGORIES = {"general", "handbook", "it", "policy"}
CHUNK_SIZE = 700
CHUNK_OVERLAP = 80


def _split_text(text: str, page_no: int | None = None) -> list[dict]:
    """按段落聚合切分，长段落按字符窗口切分。"""
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    paragraphs = [item.strip() for item in re.split(r"\n\s*\n", text) if item.strip()]
    chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        if len(paragraph) > CHUNK_SIZE:
            if buffer:
                chunks.append(buffer)
                buffer = ""
            start = 0
            while start < len(paragraph):
                chunks.append(paragraph[start : start + CHUNK_SIZE])
                start += CHUNK_SIZE - CHUNK_OVERLAP
            continue

        if len(buffer) + len(paragraph) + 1 <= CHUNK_SIZE:
            buffer = f"{buffer}\n{paragraph}".strip()
        else:
            if buffer:
                chunks.append(buffer)
            buffer = paragraph

    if buffer:
        chunks.append(buffer)

    return [{"content": chunk, "page_no": page_no} for chunk in chunks if chunk.strip()]


def extract_chunks(file_path: str, file_type: str) -> list[dict]:
    """解析 PDF / DOCX / Markdown / 纯文本为切片。"""
    suffix = file_type.lower()
    chunks: list[dict] = []

    if suffix == "pdf":
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        for index, page in enumerate(reader.pages, start=1):
            chunks.extend(_split_text(page.extract_text() or "", page_no=index))
        return chunks

    if suffix == "docx":
        from docx import Document

        document = Document(file_path)
        text = "\n".join(
            paragraph.text for paragraph in document.paragraphs if paragraph.text
        )
        return _split_text(text)

    text = Path(file_path).read_text(encoding="utf-8", errors="ignore")
    return _split_text(text)


def to_response(document: KnowledgeDocument) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=document.id,
        name=document.name,
        category=document.category,
        filename=document.filename,
        file_type=document.file_type,
        file_size=document.file_size,
        status=document.status,
        chunk_count=document.chunk_count,
        embedding_model=document.embedding_model,
        error_message=document.error_message,
        uploaded_by=document.uploaded_by,
        uploader_name=document.uploader.name if document.uploader else "",
        create_time=document.create_time,
        update_time=document.update_time,
    )


def get_document(db: Session, document_id: int) -> KnowledgeDocument:
    document = (
        db.query(KnowledgeDocument)
        .options(joinedload(KnowledgeDocument.uploader))
        .filter(KnowledgeDocument.id == document_id)
        .first()
    )
    if not document:
        raise BusinessException(message="文档不存在", code=404)
    return document


def save_document(
    db: Session,
    user: User,
    *,
    original_filename: str,
    content: bytes,
    name: str | None,
    category: str,
) -> KnowledgeDocument:
    """校验并保存上传文件，创建待索引文档。"""
    ext = Path(original_filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXTENSIONS:
        raise BusinessException(
            message="仅支持 PDF、DOCX、Markdown、TXT 文件", code=415
        )
    if not content:
        raise BusinessException(message="文件内容为空")

    max_bytes = settings.KNOWLEDGE_MAX_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise BusinessException(
            message=f"文件不能超过 {settings.KNOWLEDGE_MAX_MB} MB", code=413
        )

    category = category if category in ALLOWED_CATEGORIES else "general"
    target_dir = Path(settings.UPLOAD_DIR) / "knowledge"
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}.{ext}"
    file_path = target_dir / stored_name
    file_path.write_bytes(content)

    document = KnowledgeDocument(
        name=(name or Path(original_filename).stem or "未命名文档").strip(),
        category=category,
        filename=original_filename,
        file_path=str(file_path),
        file_type=ext,
        file_size=len(content),
        status=DOC_PENDING,
        chunk_count=0,
        uploaded_by=user.id,
        error_message="等待建立索引",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def list_documents(
    db: Session,
    user: User,
    *,
    keyword: str | None,
    category: str | None,
    page: int,
    page_size: int,
) -> PageResponse:
    """员工仅可见已就绪文档，管理员可见全部状态。"""
    can_manage = has_permission(user, PERM_KB_MANAGE)
    query = db.query(KnowledgeDocument)
    if not can_manage:
        # 员工可见正在处理或已就绪的文档，失败文档仅管理员可见
        query = query.filter(KnowledgeDocument.status != DOC_FAILED)
    if keyword:
        query = query.filter(
            or_(
                KnowledgeDocument.name.ilike(f"%{keyword}%"),
                KnowledgeDocument.filename.ilike(f"%{keyword}%"),
            )
        )
    if category:
        query = query.filter(KnowledgeDocument.category == category)

    total = query.count()
    items = (
        query.options(joinedload(KnowledgeDocument.uploader))
        .order_by(KnowledgeDocument.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PageResponse(list=[to_response(item) for item in items], total=total)


def prepare_reindex(db: Session, document_id: int) -> KnowledgeDocument:
    document = get_document(db, document_id)
    document.status = DOC_PROCESSING
    document.error_message = None
    db.commit()
    db.refresh(document)
    return document


def index_document(document_id: int) -> None:
    """后台任务：解析、切分、向量化并写入 Chroma。"""
    db = SessionLocal()
    document: KnowledgeDocument | None = None
    try:
        document = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.id == document_id)
            .first()
        )
        if document is None:
            return

        document.status = DOC_PROCESSING
        document.error_message = None
        db.commit()

        chunks = extract_chunks(document.file_path, document.file_type)
        if not chunks:
            raise ValueError("未解析到文本，可能是扫描版文件或文件内容为空")

        vectors = vector_store.embed_texts([chunk["content"] for chunk in chunks])
        vector_store.delete_document(document.id)
        vector_ids = vector_store.upsert_chunks(
            document.id, document.name, chunks, vectors
        )

        db.query(KnowledgeChunk).filter(
            KnowledgeChunk.document_id == document.id
        ).delete()
        for index, (chunk, vector_id) in enumerate(zip(chunks, vector_ids)):
            db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk["content"],
                    page_no=chunk.get("page_no"),
                    vector_id=vector_id,
                )
            )

        document.chunk_count = len(chunks)
        document.embedding_model = settings.EMBEDDING_MODEL
        document.status = DOC_READY
        document.error_message = None
        db.commit()
        logger.info(
            "知识库索引完成：document_id=%s chunks=%s", document.id, len(chunks)
        )
    except Exception as exc:
        db.rollback()
        logger.exception("知识库索引失败：document_id=%s", document_id)
        failed = (
            db.query(KnowledgeDocument)
            .filter(KnowledgeDocument.id == document_id)
            .first()
        )
        if failed is not None:
            failed.status = DOC_FAILED
            failed.error_message = str(exc)[:500]
            db.commit()
    finally:
        db.close()


def delete_document(db: Session, document_id: int) -> None:
    document = get_document(db, document_id)
    vector_store.delete_document(document.id)
    try:
        Path(document.file_path).unlink(missing_ok=True)
    except OSError:
        logger.warning("删除文件失败：%s", document.file_path, exc_info=True)
    db.delete(document)
    db.commit()


def search_knowledge(db: Session, query: str, top_k: int = 5) -> list[dict]:
    """检索知识库，仅返回仍然存在且已就绪的文档切片。"""
    if not query.strip():
        return []
    items = vector_store.search(query, top_k=top_k)
    if not items:
        return []

    document_ids = {item["document_id"] for item in items}
    documents = {
        document.id: document
        for document in db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.id.in_(document_ids),
            KnowledgeDocument.status == DOC_READY,
        )
        .all()
    }

    results: list[dict] = []
    for item in items:
        document = documents.get(item["document_id"])
        if document is None:
            continue
        results.append(
            {
                "document_id": document.id,
                "document_name": document.name,
                "chunk_index": item["chunk_index"],
                "content": item["content"],
                "score": item["score"],
                "page_no": item.get("page_no"),
            }
        )
    return results
