/**
 * Code Editor with Ghost Text support
 *
 * A code editor component with inline completion suggestions (Ghost Text).
 */

import { useRef, useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Textarea } from '@evoloop/shared/components/ui/textarea';
import { cn } from '@evoloop/shared/lib/utils';
import { useGhostText } from '@/hooks/useGhostText';
import { GhostText } from './GhostText';

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  filePath?: string;
  placeholder?: string;
  className?: string;
  language?: string;
  readOnly?: boolean;
}

export function CodeEditor({
  value,
  onChange,
  filePath = 'untitled.txt',
  placeholder,
  className,
  language,
  readOnly = false,
}: CodeEditorProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [cursorLine, setCursorLine] = useState(1);
  const [cursorColumn, setCursorColumn] = useState(0);

  const {
    state: ghostState,
    requestSuggestion,
    acceptSuggestion,
    dismissSuggestion,
  } = useGhostText({
    onAccept: (suggestion) => {
      if (!textareaRef.current) return;

      const textarea = textareaRef.current;
      const start = textarea.selectionStart;
      const newValue = value.substring(0, start) + suggestion.text + value.substring(start);

      onChange(newValue);

      // Move cursor after inserted text
      setTimeout(() => {
        const newPos = start + suggestion.text.length;
        textarea.setSelectionRange(newPos, newPos);
        textarea.focus();
      }, 0);
    },
  });

  // Calculate cursor position (line and column)
  const calculateCursorPosition = useCallback(
    (position: number): { line: number; column: number; lineText: string } => {
      const lines = value.substring(0, position).split('\n');
      const line = lines.length;
      const column = lines[lines.length - 1].length;
      const allLines = value.split('\n');
      const lineText = allLines[line - 1] || '';
      return { line, column, lineText };
    },
    [value]
  );

  // Handle input changes
  const handleInput = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value);

      // Get cursor position
      const position = e.target.selectionStart;
      const { line, column, lineText } = calculateCursorPosition(position);

      setCursorLine(line);
      setCursorColumn(column);

      // Request Ghost Text suggestion
      requestSuggestion({
        filePath,
        cursorLine: line,
        cursorColumn: column,
        currentLineText: lineText.substring(0, column),
      });
    },
    [onChange, filePath, calculateCursorPosition, requestSuggestion]
  );

  // Handle keydown for Tab (accept) and Escape (dismiss)
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (ghostState.visible) {
        if (e.key === 'Tab') {
          e.preventDefault();
          acceptSuggestion();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          dismissSuggestion();
        }
      }
    },
    [ghostState.visible, acceptSuggestion, dismissSuggestion]
  );

  // Handle click to update cursor position
  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLTextAreaElement>) => {
      const textarea = e.currentTarget;
      const position = textarea.selectionStart;
      const { line, column } = calculateCursorPosition(position);

      setCursorLine(line);
      setCursorColumn(column);
      dismissSuggestion();
    },
    [calculateCursorPosition, dismissSuggestion]
  );

  // Handle selection change
  const handleSelect = useCallback(
    (e: React.SyntheticEvent<HTMLTextAreaElement>) => {
      const textarea = e.currentTarget;
      const position = textarea.selectionStart;
      const { line, column } = calculateCursorPosition(position);

      setCursorLine(line);
      setCursorColumn(column);
    },
    [calculateCursorPosition]
  );

  return (
    <div className={cn('relative flex flex-col h-full', className)}>
      {/* Status bar */}
      <div className="flex items-center justify-between px-3 py-1.5 bg-muted/30 border-b text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>{filePath.split('/').pop()}</span>
          {language && (
            <span className="px-1.5 py-0.5 bg-muted rounded text-[10px]">{language}</span>
          )}
        </div>
        <div className="flex items-center gap-4">
            {t('editor.line')} {cursorLine}, {t('editor.column')} {cursorColumn}
          {ghostState.loading && (
            <span className="text-primary animate-pulse">
              {t('editor.thinking')}
            </span>
          )}
        </div>
      </div>

      {/* Editor area */}
      <div className="relative flex-1">
        <Textarea
          ref={textareaRef}
          className="absolute inset-0 resize-none rounded-none border-0 font-mono text-sm leading-relaxed p-4 focus-visible:ring-0 whitespace-pre"
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          onClick={handleClick}
          onSelect={handleSelect}
          placeholder={placeholder}
          readOnly={readOnly}
          spellCheck={false}
        />

        {/* Ghost Text overlay */}
        <GhostText
          state={ghostState}
          onAccept={acceptSuggestion}
          onDismiss={dismissSuggestion}
          className="absolute pointer-events-none"
          style={{
            // Position near cursor (simplified positioning)
            left: `${Math.min(cursorColumn * 8 + 16, 600)}px`,
            top: `${(cursorLine - 1) * 21 + 16}px`,
          }}
        />
      </div>

      {/* Ghost Text hint */}
      {ghostState.visible && (
        <div className="absolute bottom-2 right-2 text-[10px] text-muted-foreground bg-background/80 px-2 py-1 rounded border">
          {t('editor.ghostHint')}
        </div>
      )}
    </div>
  );
}
