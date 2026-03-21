/**
 * Ghost Text (Inline Completion) Hook
 *
 * Provides inline code completion functionality.
 * Uses OpenAPI-generated GhostTextService for type-safe API calls.
 */

import { useState, useCallback, useRef } from 'react';
import { GhostTextService } from '@/client';
import type {
  GhostSuggestion,
  GhostTextState,
  InlineCompletionRequest,
  EditPreviewRequest,
} from '@/types/ghostText';
import type {
  InlineCompletionRequest as APIInlineCompletionRequest,
  EditPreviewRequest as APIEditPreviewRequest,
} from '@/client/types.gen';

// Debounce utility
function debounce<T extends (...args: any[]) => void>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout>;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

interface UseGhostTextOptions {
  debounceMs?: number;
  minLineLength?: number;
  onAccept?: (suggestion: GhostSuggestion) => void;
  onDismiss?: () => void;
}

// Local fallback for offline/pattern matching
function getLocalSuggestion(
  request: InlineCompletionRequest
): GhostSuggestion | null {
  const line = request.currentLineText || '';
  const trimmed = line.trim();

  // Function definition patterns
  if (trimmed.startsWith('def ') && !trimmed.includes('(')) {
    return {
      text: '():',
      confidence: 0.9,
      type: 'completion',
      source: 'pattern',
      displayText: '():',
      description: 'Function definition',
    };
  }

  if (trimmed.startsWith('class ') && !trimmed.includes(':')) {
    return {
      text: ':',
      confidence: 0.95,
      type: 'completion',
      source: 'pattern',
      displayText: ':',
      description: 'Class definition',
    };
  }

  if (trimmed === 'if' || trimmed === 'elif' || trimmed === 'while') {
    return {
      text: ' condition:',
      confidence: 0.85,
      type: 'completion',
      source: 'pattern',
      displayText: ' condition:',
      description: 'Add condition',
    };
  }

  if (trimmed === 'for') {
    return {
      text: ' item in items:',
      confidence: 0.8,
      type: 'completion',
      source: 'pattern',
      displayText: ' item in items:',
      description: 'For loop pattern',
    };
  }

  if (trimmed.startsWith('from ')) {
    return {
      text: 'module import ',
      confidence: 0.85,
      type: 'completion',
      source: 'pattern',
      displayText: 'module import ',
      description: 'Import statement',
    };
  }

  return null;
}

export function useGhostText(options: UseGhostTextOptions = {}) {
  const { debounceMs = 300, minLineLength = 3 } = options;

  const [state, setState] = useState<GhostTextState>({
    visible: false,
    suggestion: null,
    position: null,
    loading: false,
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch suggestion from API with local fallback
  const fetchSuggestion = useCallback(
    async (request: InlineCompletionRequest): Promise<GhostSuggestion | null> => {
      try {
        // Convert to API request format
        const apiRequest: APIInlineCompletionRequest = {
          file_path: request.filePath,
          cursor_line: request.cursorLine,
          cursor_column: request.cursorColumn,
          current_line_text: request.currentLineText,
          context_lines: 10,
          project_id: request.projectId,
        };

        // Call OpenAPI-generated service
        const response = await GhostTextService.suggestInlineCompletion({
          requestBody: apiRequest,
        });

        if (response.suggestion) {
          return {
            text: response.suggestion.text,
            confidence: response.suggestion.confidence,
            type: response.suggestion.type as GhostSuggestion['type'],
            source: response.suggestion.source as GhostSuggestion['source'],
            displayText: response.suggestion.display_text || undefined,
            description: response.suggestion.description || undefined,
          };
        }

        return null;
      } catch (error) {
        // Fallback to local pattern matching
        console.warn('[GhostText] API failed, using local fallback:', error);
        return getLocalSuggestion(request);
      }
    },
    []
  );

  // Request suggestion with debounce
  const requestSuggestion = useCallback(
    debounce(async (request: InlineCompletionRequest) => {
      const line = request.currentLineText || '';

      // Skip if line is too short
      if (line.trim().length < minLineLength) {
        setState((prev) => ({ ...prev, visible: false, loading: false }));
        return;
      }

      // Cancel previous request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }

      const controller = new AbortController();
      abortControllerRef.current = controller;

      setState((prev) => ({ ...prev, loading: true }));

      try {
        const suggestion = await fetchSuggestion(request);

        if (!controller.signal.aborted) {
          if (suggestion && suggestion.confidence > 0.5) {
            setState({
              visible: true,
              suggestion,
              position: {
                line: request.cursorLine,
                column: request.cursorColumn,
              },
              loading: false,
            });
          } else {
            setState({
              visible: false,
              suggestion: null,
              position: null,
              loading: false,
            });
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          setState((prev) => ({ ...prev, loading: false }));
        }
      }
    }, debounceMs),
    [fetchSuggestion, minLineLength, debounceMs]
  );

  // Accept suggestion
  const acceptSuggestion = useCallback(() => {
    if (state.suggestion && state.visible) {
      options.onAccept?.(state.suggestion);
      setState((prev) => ({ ...prev, visible: false }));
      return state.suggestion;
    }
    return null;
  }, [state.suggestion, state.visible, options]);

  // Dismiss suggestion
  const dismissSuggestion = useCallback(() => {
    setState({
      visible: false,
      suggestion: null,
      position: null,
      loading: false,
    });
    options.onDismiss?.();
  }, [options]);

  // Show loading state
  const setLoading = useCallback((loading: boolean) => {
    setState((prev) => ({ ...prev, loading }));
  }, []);

  // Fetch edit preview
  const fetchEditPreview = useCallback(
    async (request: EditPreviewRequest) => {
      try {
        const apiRequest: APIEditPreviewRequest = {
          file_path: request.filePath,
          edit_description: request.editDescription,
          cursor_line: request.cursorLine,
          cursor_column: request.cursorColumn,
          project_id: request.projectId,
        };

        const response = await GhostTextService.previewEditGhost({
          requestBody: apiRequest,
        });

        return response.preview;
      } catch (error) {
        console.error('[GhostText] Failed to fetch edit preview:', error);
        return null;
      }
    },
    []
  );

  // List available patterns
  const listPatterns = useCallback(async (language?: string) => {
    try {
      const response = await GhostTextService.listPatterns({
        language,
      });
      return response;
    } catch (error) {
      console.error('[GhostText] Failed to list patterns:', error);
      return [];
    }
  }, []);

  return {
    state,
    requestSuggestion,
    acceptSuggestion,
    dismissSuggestion,
    setLoading,
    fetchEditPreview,
    listPatterns,
  };
}
