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

import axios from "axios"
import { OpenAPI } from "@/client/core/OpenAPI"
import type { DocumentInfo, DocumentContent, ProjectStats, DocumentListResponse } from "@/components/KnowledgeBase/types"

// Create axios instance with same base URL as OpenAPI
const apiClient = axios.create({
  baseURL: `${OpenAPI.BASE}/api/v1`,
  headers: {
    "Content-Type": "application/json",
  },
})

// Add auth token if available
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Types for new features
export interface FTSSearchResult {
  doc_id: string
  path: string
  project: string
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
    projects: Record<string, number>
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
  private static basePath = "/knowledge"

  // ============ Basic CRUD ============

  static async listDocuments(project?: string): Promise<DocumentListResponse> {
    const params = new URLSearchParams()
    if (project) params.append("project", project)
    
    const response = await apiClient.get(`${this.basePath}/documents?${params}`)
    return response.data as DocumentListResponse
  }

  static async getDocument(
    path: string,
    offset: number = 0,
    limit: number = 100
  ): Promise<DocumentContent> {
    const encodedPath = encodeURIComponent(path)
    const response = await apiClient.get(
      `${this.basePath}/documents/${encodedPath}?offset=${offset}&limit=${limit}`
    )
    return response.data as DocumentContent
  }

  static async uploadDocument(
    file: File,
    project: string = "default",
    docType: string = "doc"
  ): Promise<{ success: boolean; path?: string; error?: string }> {
    const formData = new FormData()
    formData.append("file", file)
    formData.append("project", project)
    formData.append("doc_type", docType)

    const response = await apiClient.post(`${this.basePath}/upload`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })
    return response.data as { success: boolean; path?: string; error?: string }
  }

  static async deleteDocument(path: string): Promise<{ success: boolean; message: string }> {
    const encodedPath = encodeURIComponent(path)
    const response = await apiClient.delete(`${this.basePath}/documents/${encodedPath}`)
    return response.data as { success: boolean; message: string }
  }

  // ============ Projects ============

  static async getProjects(): Promise<ProjectStats> {
    const response = await apiClient.get(`${this.basePath}/projects`)
    return response.data as ProjectStats
  }

  static async createProject(name: string): Promise<{ success: boolean; message: string }> {
    const response = await apiClient.post(`${this.basePath}/projects/${encodeURIComponent(name)}`)
    return response.data as { success: boolean; message: string }
  }

  // ============ Tags ============

  static async listTags(project?: string): Promise<{ tags: { name: string; count: number }[]; total: number }> {
    const params = new URLSearchParams()
    if (project) params.append("project", project)
    
    const response = await apiClient.get(`${this.basePath}/tags?${params}`)
    return response.data as { tags: { name: string; count: number }[]; total: number }
  }

  static async listDocuments(
    project?: string,
    tags?: string[]
  ): Promise<DocumentListResponse> {
    const params = new URLSearchParams()
    if (project) params.append("project", project)
    if (tags && tags.length > 0) params.append("tags", tags.join(","))
    
    const response = await apiClient.get(`${this.basePath}/documents?${params}`)
    return response.data as DocumentListResponse
  }

  // ============ FTS Search (New in Phase 2) ============

  /**
   * Full-text search using SQLite FTS5
   */
  static async ftsSearch(
    query: string,
    options?: {
      project?: string
      tags?: string[]
      limit?: number
      offset?: number
    }
  ): Promise<FTSSearchResponse> {
    const params = new URLSearchParams()
    params.append("q", query)
    if (options?.project) params.append("project", options.project)
    if (options?.tags) params.append("tags", options.tags.join(","))
    if (options?.limit) params.append("limit", options.limit.toString())
    if (options?.offset) params.append("offset", options.offset.toString())
    
    const response = await apiClient.get(`${this.basePath}/fts/search?${params}`)
    return response.data as FTSSearchResponse
  }

  /**
   * Get search suggestions
   */
  static async getSearchSuggestions(
    prefix: string,
    project?: string
  ): Promise<SearchSuggestion[]> {
    const params = new URLSearchParams()
    params.append("prefix", prefix)
    if (project) params.append("project", project)
    
    const response = await apiClient.get(`${this.basePath}/fts/suggest?${params}`)
    return response.data.suggestions as SearchSuggestion[]
  }

  // ============ Bulk Import (New in Phase 2) ============

  /**
   * Upload multiple files
   */
  static async bulkUpload(
    files: File[],
    project: string = "default",
    docType: string = "doc"
  ): Promise<BulkUploadResult> {
    const formData = new FormData()
    files.forEach(file => formData.append("files", file))
    formData.append("project", project)
    formData.append("doc_type", docType)

    const response = await apiClient.post(`${this.basePath}/bulk-upload`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })
    return response.data as BulkUploadResult
  }

  /**
   * Validate ZIP before upload
   */
  static async validateZip(file: File): Promise<ZipValidationResult> {
    const formData = new FormData()
    formData.append("file", file)

    const response = await apiClient.post(`${this.basePath}/validate-zip`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })
    return response.data as ZipValidationResult
  }

  /**
   * Import ZIP archive
   */
  static async importZip(
    file: File,
    project: string = "default",
    preserveStructure: boolean = true
  ): Promise<BulkUploadResult> {
    const formData = new FormData()
    formData.append("file", file)
    formData.append("project", project)
    formData.append("preserve_structure", preserveStructure.toString())

    const response = await apiClient.post(`${this.basePath}/import-zip`, formData, {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    })
    return response.data as BulkUploadResult
  }

  // ============ Analytics (New in Phase 2) ============

  /**
   * Get document citation statistics
   */
  static async getDocumentStats(path: string): Promise<DocumentStats> {
    const encodedPath = encodeURIComponent(path)
    const response = await apiClient.get(`${this.basePath}/${encodedPath}/stats`)
    return response.data as DocumentStats
  }

  /**
   * Get most popular documents
   */
  static async getPopularDocuments(
    options?: {
      project?: string
      days?: number
      limit?: number
    }
  ): Promise<PopularDocument[]> {
    const params = new URLSearchParams()
    if (options?.project) params.append("project", options.project)
    if (options?.days) params.append("days", options.days.toString())
    if (options?.limit) params.append("limit", options.limit.toString())
    
    const response = await apiClient.get(`${this.basePath}/analytics/popular?${params}`)
    return response.data.documents as PopularDocument[]
  }

  /**
   * Get usage analytics
   */
  static async getUsageAnalytics(days: number = 30): Promise<UsageAnalytics> {
    const params = new URLSearchParams()
    params.append("days", days.toString())
    
    const response = await apiClient.get(`${this.basePath}/analytics/usage?${params}`)
    return response.data as UsageAnalytics
  }

  /**
   * Get document recommendations
   */
  static async getRecommendations(path: string): Promise<{ recommendations: Array<{
    path: string
    reason: string
    relevance: number
    total_citations: number
  }> }> {
    const params = new URLSearchParams()
    params.append("path", path)
    
    const response = await apiClient.get(`${this.basePath}/recommendations?${params}`)
    return response.data
  }
}
