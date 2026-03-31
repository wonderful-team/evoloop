# Unified Event System

## Overview

All real-time events flow through a single Redis channel (`chat:{thread_id}:events`), distinguished by their `type` field.

## Event Types

### Core Events

| Event Type | Source | Purpose | Key Fields |
|------------|--------|---------|------------|
| `token` | LLM Streaming | Character-by-character output | `content: string` |
| `thinking` | Agent reasoning | Shows agent's thought process | `message: string, detail?: string` |
| `tool_start` | Tool execution begins | Tool name and params | `tool: string, params: object` |
| `tool_progress` | Tool execution progress | Progress updates | `tool: string, progress: number, message: string` |
| `tool_complete` | Tool execution success | Result summary | `tool: string, duration: number, success: true` |
| `tool_error` | Tool execution failure | Error details | `tool: string, success: false` |
| `checkpoint` | Checkpoint created | Auto/manual checkpoint | `checkpoint_id: number, name: string, file_count: number` |
| `progress` | Overall task progress | Phase completion | `current: number, total: number, message: string` |
| `complete` | Task finished | Final completion | `message: string` |

### Legacy Events (for compatibility)

| Event Type | Source | Purpose |
|------------|--------|---------|
| `step` | Activity Monitor | Step create/update |
| `artifact` | Artifact tracking | File changes |
| `state` | Agent state | Mode/task updates |
| `status` | Status changes | Running/idle/etc |
| `message` | New message | Persisted messages |
| `human_request` | HITL | Human interaction required |

## Event Structure

### Base Event
```typescript
interface BaseEvent {
  type: string;
  timestamp: string;  // ISO 8601
}
```

### Token Event (LLM Output)
```typescript
interface TokenEvent extends BaseEvent {
  type: "token";
  content: string;  // Single character or chunk
}

// Example
{
  "type": "token",
  "content": "Hel",
  "timestamp": "2026-03-21T10:30:00.000Z"
}
```

### Stream Events (Structured)
```typescript
interface StreamEvent extends BaseEvent {
  type: "thinking" | "tool_start" | "tool_progress" | "tool_complete" | "tool_error" | "checkpoint" | "progress" | "complete";
  message: string;
  data?: Record<string, any>;
  progress?: number;  // 0-100
}

// Examples

// thinking
{
  "type": "thinking",
  "message": "Analyzing codebase structure...",
  "data": { "detail": "Found 15 Python files" },
  "timestamp": "2026-03-21T10:30:01.000Z"
}

// tool_start
{
  "type": "tool_start",
  "message": "Reading file: src/main.py",
  "data": { 
    "tool": "read_file", 
    "params": { "path": "src/main.py" },
    "toolId": "tool-123456"
  },
  "timestamp": "2026-03-21T10:30:02.000Z"
}

// tool_progress
{
  "type": "tool_progress",
  "message": "Processing line 50/100...",
  "data": { "tool": "read_file", "toolId": "tool-123456" },
  "progress": 50,
  "timestamp": "2026-03-21T10:30:03.000Z"
}

// tool_complete
{
  "type": "tool_complete",
  "message": "Read 100 lines",
  "data": { 
    "tool": "read_file", 
    "toolId": "tool-123456",
    "duration": 0.5,
    "success": true
  },
  "timestamp": "2026-03-21T10:30:04.000Z"
}

// checkpoint
{
  "type": "checkpoint",
  "message": "Checkpoint created: Before refactor",
  "data": { 
    "checkpoint_id": 42, 
    "name": "Before refactor",
    "file_count": 5
  },
  "timestamp": "2026-03-21T10:30:05.000Z"
}

// progress
{
  "type": "progress",
  "message": "Step 2 of 5: Code analysis",
  "data": { "current": 2, "total": 5 },
  "progress": 40,
  "timestamp": "2026-03-21T10:30:06.000Z"
}

// complete
{
  "type": "complete",
  "message": "Task completed successfully",
  "progress": 100,
  "timestamp": "2026-03-21T10:30:07.000Z"
}
```

## Event Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        Event Sources                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  TransparentCallbackHandler                                       │
│  ├── on_llm_new_token() ──→ TokenEvent                          │
│  ├── emit_thinking() ─────→ StreamEvent(thinking)               │
│  ├── on_tool_start() ─────→ StreamEvent(tool_start)             │
│  ├── emit_tool_progress() → StreamEvent(tool_progress)          │
│  ├── on_tool_end() ───────→ StreamEvent(tool_complete)          │
│  └── on_tool_error() ─────→ StreamEvent(tool_error)             │
│                                                                   │
│  Checkpoint Tools                                                 │
│  └── create_checkpoint() ─→ StreamEvent(checkpoint)             │
│                                                                   │
│  Activity Monitor (Legacy)                                        │
│  ├── add_step() ──────────→ StepEvent                           │
│  ├── add_artifact() ──────→ ArtifactEvent                       │
│  └── update_agent_state() → StateEvent                          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Redis Channel                                  │
│              chat:{thread_id}:events                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    SSE Endpoint (stream.py)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  subscribe: chat:{thread_id}:events                               │
│                              ↓                                    │
│  parse event.type                                                 │
│                              ↓                                    │
│  route to SSE event type:                                         │
│  ├── "token" ─────────────────→ SSE event: token                  │
│  ├── "thinking"/"tool_*"/... ─→ SSE event: stream                 │
│  └── "step"/"task"/... ───────→ SSE event: activity               │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend Consumption                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ChatConnection                                                   │
│  ├── onToken(content) ─────→ Streaming text display              │
│  ├── onStream(event) ──────→ StreamStatus component              │
│  └── onActivity(snapshot) ─→ Full state refresh                  │
│                                                                   │
│  chatStore                                                        │
│  ├── streamState.currentThinking ─→ "Thinking..." indicator       │
│  ├── streamState.currentTool ─────→ Tool progress card            │
│  └── steps ───────────────────────→ Execution steps list          │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Frontend State Mapping

### StreamStatus Component State
```typescript
interface StreamState {
  currentThinking: string | null;     // From "thinking" events
  currentTool: {                      // From "tool_start"/"tool_progress"/"tool_complete"
    id: string;
    toolName: string;
    displayName: string;
    status: 'running' | 'complete' | 'error';
    progress: number;
    message: string;
    startTime: number;
    endTime?: number;
  } | null;
  overallProgress: number;            // From "progress" events
}
```

### Event to State Mapping
| Event | State Update |
|-------|-------------|
| `thinking` | `streamState.currentThinking = event.message` |
| `tool_start` | `streamState.currentTool = {status: 'running', ...}` |
| `tool_progress` | `streamState.currentTool.progress = event.progress` |
| `tool_complete` | `streamState.currentTool.status = 'complete'` |
| `tool_error` | `streamState.currentTool.status = 'error'` |
| `progress` | `streamState.overallProgress = event.progress` |
| `complete` | Reset streamState |

## Usage Examples

### Backend: Emit Tool Progress
```python
async def long_running_tool(params, callback_handler: TransparentCallbackHandler):
    for i in range(100):
        # Do work...
        
        # Emit progress every 10%
        if i % 10 == 0:
            await callback_handler.emit_tool_progress(
                tool_name="long_running_tool",
                message=f"Processing {i}/100 items...",
                progress=i
            )
```

### Frontend: Display Stream Status
```tsx
function ChatInterface() {
  const streamState = useChatStore(state => state.streamState);
  
  return (
    <div>
      <MessageList />
      <StreamStatus state={streamState} />  {/* Shows thinking + tool progress */}
      <ChatInput />
    </div>
  );
}
```

### Frontend: Handle Stream Events
```typescript
// In chatStore.ts
_processStreamEvent: (event: StreamEvent) => {
  switch (event.type) {
    case 'thinking':
      set({ streamState: { ...streamState, currentThinking: event.message }});
      break;
    case 'tool_start':
      set({ streamState: { ...streamState, currentTool: {...} }});
      break;
    // ... etc
  }
}
```

## Migration from Legacy

### Before (Dual Channel)
```
TokenEvent → events channel
StreamEvent → stream channel  ❌ (separate)
```

### After (Unified)
```
All Events → events channel ✅ (unified)
           ↓
    Distinguish by type field
```

## Benefits

1. **Simplicity**: Single channel, single subscription
2. **Ordering**: Events naturally ordered in single stream
3. **Debugging**: One place to monitor all events
4. **Extensibility**: Add new event types without infrastructure changes
5. **Type Safety**: Unified event schema with discriminated union
