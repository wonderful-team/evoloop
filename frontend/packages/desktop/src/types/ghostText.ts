/**
 * Ghost Text (Inline Code Completion) Types
 * 
 * Inline code completion suggestions.
 */

export interface GhostSuggestion {
  text: string;
  confidence: number;  // 0-1
  type: 'completion' | 'edit_preview' | 'snippet';
  source: 'pattern' | 'llm' | 'context';
  displayText?: string;  // Formatted for display
  description?: string;  // Tooltip description
}

export interface GhostTextState {
  visible: boolean;
  suggestion: GhostSuggestion | null;
  position: {
    line: number;
    column: number;
  } | null;
  loading: boolean;
}

export interface InlineCompletionRequest {
  filePath: string;
  cursorLine: number;
  cursorColumn: number;
  currentLineText?: string;
  projectId?: number;
}

export interface InlineCompletionResponse {
  suggestion: GhostSuggestion | null;
  alternativeSuggestions?: GhostSuggestion[];
}

export interface EditPreviewRequest {
  filePath: string;
  editDescription: string;
  cursorLine: number;
  cursorColumn: number;
  projectId?: number;
}

export interface EditPreviewResponse {
  preview: {
    originalText: string;
    suggestedText: string;
    description: string;
  } | null;
}
