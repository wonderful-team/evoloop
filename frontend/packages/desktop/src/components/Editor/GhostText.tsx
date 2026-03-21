/**
 * Ghost Text (Inline Code Completion) Component
 * 
 * Displays inline code completion suggestions.
 */

import { useEffect, useRef } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@evoloop/shared/lib/utils';
import type { GhostTextState } from '@/types/ghostText';

interface GhostTextProps {
  state: GhostTextState;
  onAccept: () => void;
  onDismiss: () => void;
  className?: string;
  style?: React.CSSProperties;
}

export function GhostText({ state, onAccept, onDismiss, className, style }: GhostTextProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // Handle keyboard events
  useEffect(() => {
    if (!state.visible) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Tab') {
        e.preventDefault();
        onAccept();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        onDismiss();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [state.visible, onAccept, onDismiss]);

  // Handle click outside
  useEffect(() => {
    if (!state.visible) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        onDismiss();
      }
    };

    // Delay to avoid immediate dismissal
    const timeout = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 100);

    return () => {
      clearTimeout(timeout);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [state.visible, onDismiss]);

  if (!state.visible && !state.loading) return null;

  return (
    <div
      ref={containerRef}
      className={cn(
        'absolute z-50 pointer-events-none',
        className
      )}
      style={{
        // Position will be set by parent based on cursor position
        left: 0,
        top: 0,
        ...style,
      }}
    >
      {state.loading && !state.suggestion && (
        <div className="flex items-center gap-2 px-2 py-1 bg-muted/80 rounded text-xs text-muted-foreground animate-in fade-in">
          <Loader2 className="h-3 w-3 animate-spin" />
          <span>Thinking...</span>
        </div>
      )}

      {state.visible && state.suggestion && (
        <div className="flex items-center gap-1 animate-in fade-in slide-in-from-left-1">
          {/* Ghost text suggestion */}
          <span
            className={cn(
              'px-1 py-0.5 rounded text-sm font-mono whitespace-pre',
              'bg-primary/10 text-primary/60',
              'border-l-2 border-primary/40'
            )}
            title={state.suggestion.description}
          >
            {state.suggestion.displayText || state.suggestion.text}
          </span>

          {/* Tab hint */}
          <span className="ml-1 text-[10px] text-muted-foreground/60 bg-muted/50 px-1.5 py-0.5 rounded">
            Tab
          </span>

          {/* Confidence indicator (subtle) */}
          {state.suggestion.confidence > 0.9 && (
            <span className="w-1.5 h-1.5 rounded-full bg-green-500/60" title="High confidence" />
          )}
        </div>
      )}
    </div>
  );
}

// Simpler inline ghost text for textarea
interface InlineGhostTextProps {
  suggestion: string;
  visible: boolean;
  className?: string;
}

export function InlineGhostText({ suggestion, visible, className }: InlineGhostTextProps) {
  if (!visible || !suggestion) return null;

  return (
    <span
      className={cn(
        'text-muted-foreground/40 pointer-events-none select-none',
        'animate-in fade-in duration-150',
        className
      )}
    >
      {suggestion}
    </span>
  );
}
