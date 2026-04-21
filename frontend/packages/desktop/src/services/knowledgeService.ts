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

import { KnowledgeService as KnowledgeServiceSDK } from "@/client/sdk.gen"
import type {
  BulkUploadResponse,
  DocumentContentResponse,
  DocumentResponse,
  FTSSearchResponse,
  TagResponse,
  ZipImportResponse,
} from "@/client/types.gen"
import type {
  CollectionsStats,
  DocumentListResponse,
  ZipValidationResult,
} from "@/components/KnowledgeBase/types"

export type { FTSSearchResult } from "@/client/types.gen"
export type { ZipValidationResult } from "@/components/KnowledgeBase/types"

export interface SearchSuggestion {
  text: string
  path?: string
  type: "title" | "tag"
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

// biome-ignore lint/complexity/noStaticOnlyClass: Organizes KB API calls as a namespace
export class KnowledgeBaseAPI {
  // ============ Basic CRUD ============

  static async listDocuments(
    collection?: string,
    sourceProjectId?: number,
  ): Promise<DocumentListResponse> {
    const data = await KnowledgeServiceSDK.listDocuments({
      collection: collection ?? null,
      sourceProjectId,
    })
    return data
  }

  static async getDocument(
    path: string,
    offset: number = 0,
    limit: number = 100,
  ): Promise<DocumentContentResponse> {
    const data = await KnowledgeServiceSDK.readDocument({
      path,
      offset,
      limit,
    })
    return data
  }

  static async uploadDocument(
    file: File,
    collection: string = "default",
    docType: string = "doc",
  ): Promise<DocumentResponse> {
    const data = await KnowledgeServiceSDK.uploadDocument({
      formData: {
        file,
        collection,
        doc_type: docType,
      },
    })
    return data
  }

  static async deleteDocument(path: string): Promise<DocumentResponse> {
    const data = await KnowledgeServiceSDK.deleteDocument({ path })
    return data
  }

  // ============ Projects ============

  static async getCollections(): Promise<CollectionsStats> {
    const data = await KnowledgeServiceSDK.listCollections()
    return data as unknown as CollectionsStats
  }

  static async createProject(name: string): Promise<DocumentResponse> {
    return KnowledgeBaseAPI.createCollection(name)
  }

  static async createCollection(name: string): Promise<DocumentResponse> {
    const data = await KnowledgeServiceSDK.createCollection({ name })
    return data
  }

  // ============ Tags ============

  static async listTags(collection?: string): Promise<TagResponse> {
    const data = await KnowledgeServiceSDK.listTags({
      collection: collection ?? null,
    })
    return data
  }

  // ============ FTS Search ============

  static async ftsSearch(
    query: string,
    options?: { collection?: string; tags?: string[] },
  ): Promise<FTSSearchResponse> {
    const data = await KnowledgeServiceSDK.ftsSearch({
      q: query,
      collection: options?.collection ?? null,
      tags: options?.tags?.join(",") ?? null,
    })
    return data
  }

  // ============ Popular Documents ============

  static async getPopularDocuments(options?: {
    days?: number
    limit?: number
  }): Promise<PopularDocument[]> {
    const data = await KnowledgeServiceSDK.getPopularDocuments({
      days: options?.days,
      limit: options?.limit,
    })
    return (data as { documents?: PopularDocument[] }).documents || []
  }

  // ============ Bulk Upload ============

  static async bulkUpload(
    files: File[],
    collection: string = "default",
    docType: string = "doc",
  ): Promise<BulkUploadResponse> {
    const data = await KnowledgeServiceSDK.bulkUpload({
      formData: {
        files,
        collection,
        doc_type: docType,
      },
    })
    return data
  }

  // ============ ZIP Import ============

  static async importZip(
    file: File,
    collection: string = "default",
    preserveStructure: boolean = true,
  ): Promise<ZipImportResponse> {
    const data = await KnowledgeServiceSDK.importZip({
      formData: {
        file,
        collection,
        preserve_structure: preserveStructure,
      },
    })
    return data
  }

  // ============ ZIP Validation ============

  static async validateZip(file: File): Promise<ZipValidationResult> {
    const data = await KnowledgeServiceSDK.validateZip({
      formData: { file },
    })
    return data as unknown as ZipValidationResult
  }

  // ============ Document Stats ============

  static async getDocumentStats(path: string): Promise<DocumentStats> {
    const data = await KnowledgeServiceSDK.getDocumentStats({ path })
    return data as unknown as DocumentStats
  }

  // ============ Recommendations ============

  static async getRecommendations(path: string): Promise<{
    recommendations: {
      path: string
      reason: string
      collection?: string
      relevance?: number
    }[]
  }> {
    const data = await KnowledgeServiceSDK.getRecommendations({ path })
    return data as unknown as {
      recommendations: {
        path: string
        reason: string
        collection?: string
        relevance?: number
      }[]
    }
  }
}
