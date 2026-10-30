from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.common.exceptions import BusinessException
from app.common.response import Response
from app.core.constants import PERM_KB_MANAGE, PERM_KB_VIEW
from app.database import get_db
from app.dependencies.auth import require_permissions
from app.models.user import User
from app.services import knowledge_service

router = APIRouter(prefix="/knowledge", tags=["知识库"])


@router.get("/documents")
def get_documents(
    keyword: str | None = Query(default=None),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_permissions(PERM_KB_VIEW)),
    db: Session = Depends(get_db),
):
    """文档列表：员工仅见已就绪文档，管理员可见全部状态。"""
    result = knowledge_service.list_documents(
        db,
        current_user,
        keyword=keyword,
        category=category,
        page=page,
        page_size=page_size,
    )
    return Response.success(data=result)


@router.post("/documents")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    category: str = Form(default="general"),
    current_user: User = Depends(require_permissions(PERM_KB_MANAGE)),
    db: Session = Depends(get_db),
):
    """上传文档并异步建立索引。"""
    content = await file.read()
    document = knowledge_service.save_document(
        db,
        current_user,
        original_filename=file.filename or "未命名文件",
        content=content,
        name=name,
        category=category,
    )
    background_tasks.add_task(knowledge_service.index_document, document.id)
    return Response.success(
        message="上传成功，正在建立索引", data=knowledge_service.to_response(document)
    )


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    current_user: User = Depends(require_permissions(PERM_KB_VIEW)),
    db: Session = Depends(get_db),
):
    """下载原文件。"""
    document = knowledge_service.get_document(db, document_id)
    path = Path(document.file_path)
    if not path.exists():
        raise BusinessException(message="文件不存在", code=404)
    return FileResponse(path, filename=document.filename)


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(require_permissions(PERM_KB_MANAGE)),
    db: Session = Depends(get_db),
):
    """删除文档、切片与向量。"""
    knowledge_service.delete_document(db, document_id)
    return Response.success(message="删除成功")


@router.post("/documents/{document_id}/reindex")
def reindex_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_permissions(PERM_KB_MANAGE)),
    db: Session = Depends(get_db),
):
    """重建单个文档索引。"""
    knowledge_service.prepare_reindex(db, document_id)
    background_tasks.add_task(knowledge_service.index_document, document_id)
    return Response.success(message="已提交重建索引")


@router.get("/search")
def search_knowledge(
    q: str = Query(min_length=1),
    top_k: int = Query(default=5, ge=1, le=20),
    current_user: User = Depends(require_permissions(PERM_KB_VIEW)),
    db: Session = Depends(get_db),
):
    """知识库语义检索。"""
    items = knowledge_service.search_knowledge(db, q, top_k=top_k)
    return Response.success(data={"query": q, "items": items})
