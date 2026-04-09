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

import { KnowledgeService as SDKKnowledgeService } from "@/client"
import type { DocumentContent, ProjectStats, DocumentListResponse } from "@/components/KnowledgeBase/types"

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
  // ============ Basic CRUD ============

  static async listDocuments(project?: string): Promise<DocumentListResponse> {
    const response = await SDKKnowledgeService.listDocuments({ project })
    return response as unknown as DocumentListResponse
  }

  static async getDocument(
    path: string,
    offset: number = 0,
    limit: number = 100
  ): Promise<DocumentContent> {
    const response = await SDKKnowledgeService.readDocument({ path, offset, limit })
    return response as unknown as DocumentContent
  }

  static async uploadDocument(
    file: File,
    project: string = "default",
    docType: string = "doc"
  ): Promise<{ success: boolean; path?: string; error?: string }> {
    const formData = {
      file,
      project,
      doc_type: docType
    }

    const response = await SDKKnowledgeService.uploadDocument({ formData })
    return response as any
  }

  static async deleteDocument(path: string): Promise<{ success: boolean; message: string }> {
    const response = await SDKKnowledgeService.deleteDocument({ path })
    return response as unknown as { success: boolean; message: string }
  }

  // ============ Projects ============

  static async getProjects(): Promise<ProjectStats> {
    const response = await SDKKnowledgeService.listProjects()
    return response as unknown as ProjectStats
  }

  static async createProject(name: string): Promise<{ success: boolean; message: string }> {
    const response = await SDKKnowledgeService.createProject({ name })
    return response as unknown as { success: boolean; message: string }
  }

  // ============ Tags ============

  static async listTags(project?: string): Promise<{ tags: { name: string; count: number }[]; total: number }> {
    const response = await SDKKnowledgeService.listTags({ project })
    return response as any
  }

  static async listDocumentsWithTags(
    project?: string,
    tags?: string[]
  ): Promise<DocumentListResponse> {
    const response = await SDKKnowledgeService.listDocuments({
      project,
      tags: tags?.join(",")
    })
    return response as unknown as DocumentListResponse
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
    const response = await SDKKnowledgeService.ftsSearch({
      q: query,
      project: options?.project,
      tags: options?.tags?.join(","),
      limit: options?.limit,
      offset: options?.offset
    })
    return response as FTSSearchResponse
  }

  /**
   * Get search suggestions
   */
  static async getSearchSuggestions(
    prefix: string,
    project?: string
  ): Promise<SearchSuggestion[]> {
    const response = await SDKKnowledgeService.ftsSuggest({
      prefix,
      project
    })
    const data = response as any
    return (data.suggestions || []) as SearchSuggestion[]
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
    const formData = {
      files,
      project,
      doc_type: docType
    }

    const response = await SDKKnowledgeService.bulkUpload({ formData })
    return response as BulkUploadResult
  }

  /**
   * Validate ZIP before upload
   */
  static async validateZip(file: File): Promise<ZipValidationResult> {
    const formData = { file }

    const response = await SDKKnowledgeService.validateZip({ formData })
    return response as ZipValidationResult
  }

  /**
   * Import ZIP archive
   */
  static async importZip(
    file: File,
    project: string = "default",
    preserveStructure: boolean = true
  ): Promise<BulkUploadResult> {
    const formData = {
      file,
      project,
      preserve_structure: preserveStructure
    }

    const response = await SDKKnowledgeService.importZip({ formData })
    return response as BulkUploadResult
  }

  // ============ Analytics (New in Phase 2) ============

  /**
   * Get document citation statistics
   */
  static async getDocumentStats(path: string): Promise<DocumentStats> {
    const response = await SDKKnowledgeService.getDocumentStats({ path })
    return response as DocumentStats
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
    const response = await SDKKnowledgeService.getPopularDocuments({
      project: options?.project,
      days: options?.days,
      limit: options?.limit
    })
    const data = response as any
    return (data.documents || []) as PopularDocument[]
  }

  /**
   * Get usage analytics
   */
  static async getUsageAnalytics(days: number = 30): Promise<UsageAnalytics> {
    const response = await SDKKnowledgeService.getUsageAnalytics({ days })
    return response as UsageAnalytics
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
    const response = await SDKKnowledgeService.getRecommendations({ path })
    return response as any
  }
}
