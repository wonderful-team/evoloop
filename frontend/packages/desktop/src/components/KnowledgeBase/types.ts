export interface DocumentInfo {
  path: string
  title?: string
  source?: string
  size_bytes: number
  modified_at: string
  has_metadata: boolean
  collection?: string
  tags?: string[] // New in Phase 2
}

export interface DocumentContent {
  path: string
  content: string
  metadata?: Record<string, unknown>
  offset: number
  limit: number
  total_lines: number
  has_more: boolean
}

export interface UploadResult {
  success: boolean
  path?: string
  error?: string
}

export interface CollectionsStats {
  collections: string[]
  stats: {
    total_documents: number
    total_size_bytes: number
    collections: Record<string, { documents: number; size_bytes: number }>
  }
}

export interface DocumentListResponse {
  total: number
  documents: DocumentInfo[]
  collections: string[]
}

// Phase 2 new types
export interface FTSSearchResult {
  doc_id: string
  path: string
  collection: string
  title: string
  snippet: string
  highlights: string // HTML with <mark> tags
  score: number
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
