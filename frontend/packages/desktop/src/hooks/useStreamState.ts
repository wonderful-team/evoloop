/**
 * Stream State Hook for real-time updates
 * 
 * Manages enhanced streaming state for transparent agent execution.
 */

import { useState, useCallback, useRef } from 'react';
import type { 
  StreamEvent, 
  StreamState, 
  ToolExecutionStatus,
  ThinkingContent 
} from '@/types/stream';

const MAX_EVENTS = 100;
const MAX_THINKING_ITEMS = 10;

export function useStreamState() {
  const [state, setState] = useState<StreamState>({
    events: [],
    currentThinking: null,
    currentTool: null,
    overallProgress: 0,
  });

  const [thinkingHistory, setThinkingHistory] = useState<ThinkingContent[]>([]);
  const [toolHistory, setToolHistory] = useState<ToolExecutionStatus[]>([]);
  
  const toolMapRef = useRef<Map<string, ToolExecutionStatus>>(new Map());

  // Process incoming stream event
  const processEvent = useCallback((event: StreamEvent) => {
    setState(prev => {
      const newEvents = [...prev.events, event].slice(-MAX_EVENTS);
      
      switch (event.type) {
        case 'thinking':
          return {
            ...prev,
            events: newEvents,
            currentThinking: event.message,
          };
          
        case 'tool_start':
          const toolId = event.data?.toolId || `tool-${Date.now()}`;
          const newTool: ToolExecutionStatus = {
            id: toolId,
            toolName: event.data?.toolName || 'Unknown Tool',
            displayName: event.data?.displayName || event.data?.toolName || 'Unknown Tool',
            status: 'running',
            progress: 0,
            message: event.message,
            startTime: event.timestamp,
            params: event.data?.params,
          };
          
          toolMapRef.current.set(toolId, newTool);
          setToolHistory(prev => [...prev, newTool].slice(-20));
          
          return {
            ...prev,
            events: newEvents,
            currentTool: newTool,
          };
          
        case 'tool_progress':
          const runningToolId = event.data?.toolId;
          if (runningToolId && toolMapRef.current.has(runningToolId)) {
            const existing = toolMapRef.current.get(runningToolId)!;
            const updated = {
              ...existing,
              progress: event.progress || existing.progress,
              message: event.message,
            };
            toolMapRef.current.set(runningToolId, updated);
            
            setToolHistory(prev => 
              prev.map(t => t.id === runningToolId ? updated : t)
            );
            
            return {
              ...prev,
              events: newEvents,
              currentTool: updated,
            };
          }
          return { ...prev, events: newEvents };
          
        case 'tool_complete':
          const completeToolId = event.data?.toolId;
          if (completeToolId && toolMapRef.current.has(completeToolId)) {
            const existing = toolMapRef.current.get(completeToolId)!;
            const completed = {
              ...existing,
              status: 'complete' as const,
              progress: 100,
              message: event.message,
              endTime: event.timestamp,
              result: event.data?.result,
            };
            toolMapRef.current.set(completeToolId, completed);
            
            setToolHistory(prev => 
              prev.map(t => t.id === completeToolId ? completed : t)
            );
            
            return {
              ...prev,
              events: newEvents,
              currentTool: completed,
            };
          }
          return { ...prev, events: newEvents };
          
        case 'tool_error':
          const errorToolId = event.data?.toolId;
          if (errorToolId && toolMapRef.current.has(errorToolId)) {
            const existing = toolMapRef.current.get(errorToolId)!;
            const errored = {
              ...existing,
              status: 'error' as const,
              message: event.message,
              endTime: event.timestamp,
              error: event.data?.error,
            };
            toolMapRef.current.set(errorToolId, errored);
            
            setToolHistory(prev => 
              prev.map(t => t.id === errorToolId ? errored : t)
            );
            
            return {
              ...prev,
              events: newEvents,
              currentTool: errored,
            };
          }
          return { ...prev, events: newEvents };
          
        case 'checkpoint':
          // Checkpoint events are logged but don't change current state
          return {
            ...prev,
            events: newEvents,
          };
          
        case 'progress':
          return {
            ...prev,
            events: newEvents,
            overallProgress: event.progress || prev.overallProgress,
          };
          
        case 'complete':
          return {
            ...prev,
            events: newEvents,
            currentThinking: null,
            currentTool: null,
            overallProgress: 100,
          };
          
        default:
          return { ...prev, events: newEvents };
      }
    });

    // Add to thinking history
    if (event.type === 'thinking') {
      setThinkingHistory(prev => {
        const newItem: ThinkingContent = {
          id: `think-${Date.now()}-${Math.random()}`,
          content: event.message,
          timestamp: event.timestamp,
        };
        return [...prev, newItem].slice(-MAX_THINKING_ITEMS);
      });
    }
  }, []);

  // Clear all state
  const clearState = useCallback(() => {
    setState({
      events: [],
      currentThinking: null,
      currentTool: null,
      overallProgress: 0,
    });
    setThinkingHistory([]);
    setToolHistory([]);
    toolMapRef.current.clear();
  }, []);

  // Get current running tools
  const getRunningTools = useCallback(() => {
    return Array.from(toolMapRef.current.values())
      .filter(t => t.status === 'running')
      .sort((a, b) => a.startTime - b.startTime);
  }, []);

  return {
    state,
    thinkingHistory,
    toolHistory,
    processEvent,
    clearState,
    getRunningTools,
  };
}
