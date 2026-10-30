from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DOC_PENDING
from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = {"comment": "知识库文档表"}

    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="文档名称")
    category: Mapped[str] = mapped_column(
        String(50), nullable=False, default="general", comment="分类"
    )
    filename: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="原始文件名"
    )
    file_path: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="存储路径"
    )
    file_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="文件类型"
    )
    file_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, comment="文件大小（字节）"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DOC_PENDING, comment="索引状态"
    )
    chunk_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="切片数量"
    )
    embedding_model: Mapped[str | None] = mapped_column(
        String(100), comment="向量模型"
    )
    error_message: Mapped[str | None] = mapped_column(
        String(500), comment="失败原因"
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, comment="上传人ID"
    )

    uploader: Mapped[User] = relationship()
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_knowledge_chunk_index"
        ),
        Index("ix_knowledge_chunk_doc", "document_id"),
        {"comment": "知识库切片表"},
    )

    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="文档ID",
    )
    chunk_index: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="切片序号"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="切片内容")
    page_no: Mapped[int | None] = mapped_column(Integer, comment="页码")
    vector_id: Mapped[str | None] = mapped_column(
        String(100), comment="向量库记录ID"
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")
