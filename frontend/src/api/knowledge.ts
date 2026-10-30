import { request } from '@/utils/request'
import type { KnowledgeDocument, PageResult } from '@/types'

export interface KnowledgeQuery {
  keyword?: string
  category?: string
  page?: number
  page_size?: number
}

/** 文档列表 */
export function getDocumentsApi(params: KnowledgeQuery = {}) {
  return request<PageResult<KnowledgeDocument>>({
    url: '/api/knowledge/documents',
    method: 'get',
    params
  })
}

/** 上传文档（仅管理员） */
export function uploadDocumentApi(file: File, name?: string, category = 'general') {
  const form = new FormData()
  form.append('file', file)
  if (name) form.append('name', name)
  form.append('category', category)
  return request<KnowledgeDocument>({
    url: '/api/knowledge/documents',
    method: 'post',
    data: form
  })
}

/** 删除文档（仅管理员） */
export function deleteDocumentApi(id: number) {
  return request<null>({
    url: `/api/knowledge/documents/${id}`,
    method: 'delete'
  })
}

/** 重建索引（仅管理员） */
export function reindexDocumentApi(id: number) {
  return request<null>({
    url: `/api/knowledge/documents/${id}/reindex`,
    method: 'post'
  })
}
