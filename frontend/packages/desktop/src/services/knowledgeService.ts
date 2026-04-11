/**
 * Knowledge Base Service - 知识库文档管理 (Phase 2)
 * 
 * 功能:
 * - 列出文档和项目
 * - 获取文档内容
 * - 上传新文档 (单文件/批量/ZIP)
 * - FTS 全文搜索
 * - 标签和分类
 * - 引用统计和分析
 */

import { OpenAPI } from "@/client"
import type { DocumentContent, CollectionsStats, DocumentListResponse } from "@/components/KnowledgeBase/types"

// Types for new features
export interface FTSSearchResult {
  doc_id: string
  path: string
  collection: string
  title: string
  snippet: string
  highlights: string
  score: number
}

export interface FTSSearchResponse {
  query: string
  total: number
  results: FTSSearchResult[]
  facets: {
    collections: Record<string, number>
    tags: Record<string, number>
  }
}

export interface SearchSuggestion {
  text: string
  path?: string
  type: "title" | "tag"
}

export interface BulkUploadResult {
  success: boolean
  message: string
  total_files: number
  successful: number
  failed: number
  imported_paths: string[]
}

export interface ZipValidationResult {
  valid: boolean
  total_files: number
  processable_files: number
  total_size_bytes: number
  compressed_size_bytes: number
  sample_files: string[]
  error?: string
}

export interface DocumentStats {
  found: boolean
  path: string
  total_citations: number
  unique_sessions: number
  last_accessed?: string
  tools_used: Record<string, number>
  related_documents: string[]
}

export interface PopularDocument {
  path: string
  citations: number
  unique_sessions: number
  last_accessed?: string
  tools_used: Record<string, number>
}

export interface UsageAnalytics {
  period_days: number
  total_citations: number
  active_documents: number
  citations_by_tool: Record<string, number>
  popular_tags: string[]
  most_cited: string[]
}

export class KnowledgeService {
  // ============ Basic CRUD ============

  static async listDocuments(collection?: string, sourceProjectId?: number): Promise<DocumentListResponse> {
    const url = new URL(`${OpenAPI.BASE}/api/v1/knowledge/documents`)
    if (collection) {
      url.searchParams.set("collection", collection)
    }
    if (sourceProjectId) {
      url.searchParams.set("source_project_id", sourceProjectId.toString())
    }
    const response = await fetch(url.toString())
    return response.json()
  }

  static async getDocument(
    path: string,
    offset: number = 0,
    limit: number = 100
  ): Promise<DocumentContent> {
    const url = new URL(`${OpenAPI.BASE}/api/v1/knowledge/documents/${encodeURIComponent(path)}`)
    url.searchParams.set("offset", offset.toString())
    url.searchParams.set("limit", limit.toString())
    const response = await fetch(url.toString())
    return response.json()
  }

  static async uploadDocument(
    file: File,
    collection: string = "default",
    docType: string = "doc"
  ): Promise<{ success: boolean; path?: string; error?: string }> {
    const formData = new FormData()
    formData.append("file", file)
    formData.append("collection", collection)
    formData.append("doc_type", docType)

    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/upload`, {
      method: "POST",
      body: formData,
    })
    return response.json()
  }

  static async deleteDocument(path: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/documents/${encodeURIComponent(path)}`, {
      method: "DELETE",
    })
    return response.json()
  }

  // ============ Projects ============

  static async getCollections(): Promise<CollectionsStats> {
    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/collections`)
    return response.json()
  }

  static async createProject(name: string): Promise<{ success: boolean; message: string }> {
    return this.createCollection(name)
  }

  static async createCollection(name: string): Promise<{ success: boolean; message: string }> {
    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/collections/${encodeURIComponent(name)}`, {
      method: "POST",
    })
    return response.json()
  }

  // ============ Tags ============

  static async listTags(collection?: string): Promise<{ tags: { name: string; count: number }[]; total: number }> {
    const url = new URL(`${OpenAPI.BASE}/api/v1/knowledge/tags`)
    if (collection) {
      url.searchParams.set("collection", collection)
    }
    const response = await fetch(url.toString())
    return response.json()
  }

  // ============ FTS Search ============

  static async ftsSearch(
    query: string,
    options?: { collection?: string; tags?: string[] }
  ): Promise<FTSSearchResponse> {
    const url = new URL(`${OpenAPI.BASE}/api/v1/knowledge/fts/search`)
    url.searchParams.set("q", query)
    if (options?.collection) {
      url.searchParams.set("collection", options.collection)
    }
    if (options?.tags && options.tags.length > 0) {
      options.tags.forEach((tag) => url.searchParams.append("tags", tag))
    }
    const response = await fetch(url.toString())
    return response.json()
  }

  // ============ Popular Documents ============

  static async getPopularDocuments(options?: { days?: number; limit?: number }): Promise<PopularDocument[]> {
    const url = new URL(`${OpenAPI.BASE}/api/v1/knowledge/analytics/popular`)
    if (options?.limit) {
      url.searchParams.set("limit", options.limit.toString())
    }
    if (options?.days) {
      url.searchParams.set("days", options.days.toString())
    }
    const response = await fetch(url.toString())
    const data = await response.json()
    return data.documents || []
  }

  // ============ Bulk Upload ============

  static async bulkUpload(
    files: File[],
    collection: string = "default",
    docType: string = "doc"
  ): Promise<BulkUploadResult> {
    const formData = new FormData()
    files.forEach((file) => formData.append("files", file))
    formData.append("collection", collection)
    formData.append("doc_type", docType)

    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/bulk-upload`, {
      method: "POST",
      body: formData,
    })
    return response.json()
  }

  // ============ ZIP Import ============

  static async importZip(
    file: File,
    collection: string = "default",
    preserveStructure: boolean = true
  ): Promise<BulkUploadResult> {
    const formData = new FormData()
    formData.append("file", file)
    formData.append("collection", collection)
    formData.append("preserve_structure", preserveStructure.toString())

    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/import-zip`, {
      method: "POST",
      body: formData,
    })
    return response.json()
  }

  // ============ ZIP Validation ============

  static async validateZip(file: File): Promise<ZipValidationResult> {
    const formData = new FormData()
    formData.append("file", file)

    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/validate-zip`, {
      method: "POST",
      body: formData,
    })
    return response.json()
  }

  // ============ Document Stats ============

  static async getDocumentStats(path: string): Promise<DocumentStats> {
    const response = await fetch(`${OpenAPI.BASE}/api/v1/knowledge/${encodeURIComponent(path)}/stats`)
    return response.json()
  }

  // ============ Recommendations ============

  static async getRecommendations(path: string): Promise<{
    recommendations: { path: string; reason: string; collection?: string; relevance?: number }[]
  }> {
    const url = new URL(`${OpenAPI.BASE}/api/v1/knowledge/recommendations`)
    url.searchParams.set("path", path)
    const response = await fetch(url.toString())
    return response.json()
  }
}
