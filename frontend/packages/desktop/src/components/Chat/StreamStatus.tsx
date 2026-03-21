/**
 * Stream Status Component for real-time updates
 * 
 * Displays real-time agent execution status with thinking and tool progress.
 */

import { useState } from 'react';
import { 
  Loader2, 
  Brain, 
  Wrench, 
  CheckCircle2, 
  XCircle,
  ChevronDown,
  ChevronUp,
  Clock,
  Camera
} from 'lucide-react';
import { cn } from '@evoloop/shared/lib/utils';
import { Button } from '@evoloop/shared/components/ui/button';
import type { StreamState, ToolExecutionStatus } from '@/types/stream';

interface StreamStatusProps {
  state: StreamState;
  className?: string;
}

function ToolStatusIcon({ status }: { status: ToolExecutionStatus['status'] }) {
  switch (status) {
    case 'running':
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />;
    case 'complete':
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />;
    case 'error':
      return <XCircle className="h-3.5 w-3.5 text-red-500" />;
    case 'pending':
      return <Clock className="h-3.5 w-3.5 text-muted-foreground" />;
  }
}

function ToolStatusItem({ tool }: { tool: ToolExecutionStatus }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 py-1.5 px-2 rounded hover:bg-muted/50 transition-colors">
        <ToolStatusIcon status={tool.status} />
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium truncate">
              {tool.displayName}
            </span>
            {tool.endTime && tool.startTime && (
              <span className="text-[10px] text-muted-foreground">
                {tool.endTime - tool.startTime}ms
              </span>
            )}
          </div>
          
          {tool.message && (
            <p className="text-[10px] text-muted-foreground truncate">
              {tool.message}
            </p>
          )}
        </div>

        {/* Progress bar for running tools */}
        {tool.status === 'running' && tool.progress > 0 && (
          <div className="w-16 h-1 bg-muted rounded-full overflow-hidden">
            <div 
              className="h-full bg-primary transition-all duration-300"
              style={{ width: `${tool.progress}%` }}
            />
          </div>
        )}

        {/* Toggle details */}
        {tool.params && (
          <Button
            variant="ghost"
            size="sm"
            className="h-5 w-5 p-0"
            onClick={() => setShowDetails(!showDetails)}
          >
            {showDetails ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
          </Button>
        )}
      </div>

      {/* Expanded details */}
      {showDetails && tool.params && (
        <div className="ml-6 px-2 py-1.5 bg-muted/30 rounded text-[10px] font-mono overflow-x-auto">
          <pre className="whitespace-pre-wrap break-all">
            {JSON.stringify(tool.params, null, 2)}
          </pre>
        </div>
      )}

      {/* Error message */}
      {tool.error && (
        <div className="ml-6 px-2 py-1.5 bg-red-500/10 text-red-500 rounded text-[10px]">
          {tool.error}
        </div>
      )}
    </div>
  );
}

export function StreamStatus({ state, className }: StreamStatusProps) {
  const [expanded, setExpanded] = useState(true);
  const [showThinking, setShowThinking] = useState(true);

  // Don't render if nothing is happening
  if (!state.currentThinking && !state.currentTool && state.events.length === 0) {
    return null;
  }

  return (
    <div className={cn(
      'border rounded-lg bg-background/50 overflow-hidden',
      'animate-in fade-in slide-in-from-bottom-2',
      className
    )}>
      {/* Header */}
      <div 
        className="flex items-center gap-2 px-3 py-2 bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        {state.currentTool?.status === 'running' ? (
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
        ) : (
          <Brain className="h-4 w-4 text-primary" />
        )}
        
        <span className="text-xs font-medium flex-1">
          {state.currentThinking || state.currentTool?.message || 'Thinking...'}
        </span>

        {/* Progress indicator */}
        {state.overallProgress > 0 && state.overallProgress < 100 && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground">
              {state.overallProgress}%
            </span>
            <div className="w-12 h-1 bg-muted rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${state.overallProgress}%` }}
              />
            </div>
          </div>
        )}

        <Button variant="ghost" size="sm" className="h-6 w-6 p-0">
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>

      {/* Content */}
      {expanded && (
        <div className="divide-y">
          {/* Thinking Section */}
          {state.currentThinking && (
            <div className="p-3">
              <div 
                className="flex items-center gap-2 mb-2 cursor-pointer"
                onClick={() => setShowThinking(!showThinking)}
              >
                <Brain className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-medium text-muted-foreground">
                  Thinking
                </span>
              </div>
              
              {showThinking && (
                <div className="ml-5 text-xs text-muted-foreground leading-relaxed">
                  {state.currentThinking}
                </div>
              )}
            </div>
          )}

          {/* Current Tool Section */}
          {state.currentTool && (
            <div className="p-3">
              <div className="flex items-center gap-2 mb-2">
                <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-[11px] font-medium text-muted-foreground">
                  Current Tool
                </span>
              </div>
              <div className="ml-5">
                <ToolStatusItem tool={state.currentTool} />
              </div>
            </div>
          )}

          {/* Checkpoint indicator */}
          {state.events.some(e => e.type === 'checkpoint') && (
            <div className="p-2 px-3 bg-blue-500/5">
              <div className="flex items-center gap-2">
                <Camera className="h-3 w-3 text-blue-500" />
                <span className="text-[10px] text-blue-500">
                  Checkpoint created
                </span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
