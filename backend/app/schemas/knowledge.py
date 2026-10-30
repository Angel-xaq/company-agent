from datetime import datetime

from pydantic import BaseModel


class KnowledgeDocumentResponse(BaseModel):
    id: int
    name: str
    category: str
    filename: str
    file_type: str
    file_size: int
    status: str
    chunk_count: int
    embedding_model: str | None = None
    error_message: str | None = None
    uploaded_by: int
    uploader_name: str
    create_time: datetime
    update_time: datetime


class KnowledgeSearchItem(BaseModel):
    document_id: int
    document_name: str
    chunk_index: int
    content: str
    score: float
    page_no: int | None = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    items: list[KnowledgeSearchItem]
