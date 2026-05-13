export interface ExtractedPart {
  type: 'text' | 'echarts' | 'test_report' | 'requirement_analysis';
  content?: string;
  data?: any;
}

function findMatchingBraceEnd(text: string, startIndex: number): number {
  if (text[startIndex] !== '{') return -1;
  let depth = 1;
  for (let i = startIndex + 1; i < text.length; i++) {
    const char = text[i];
    if (char === '"') {
      i++;
      while (i < text.length) {
        if (text[i] === '\\') {
          i += 2;
        } else if (text[i] === '"') {
          break;
        } else {
          i++;
        }
      }
      continue;
    }
    if (char === '{') depth++;
    if (char === '}') {
      depth--;
      if (depth === 0) return i;
    }
  }
  return -1;
}

/**
 * Extract artifact JSON blocks from message content.
 * Supports whole-message JSON, inline JSON, and code-block JSON.
 */
export function extractArtifactBlocks(content: string): ExtractedPart[] {
  const trimmed = content.trim();
  if (!trimmed) return [{ type: 'text', content: '' }];

  // Fast path: whole message is a single artifact
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
    try {
      const obj = JSON.parse(trimmed);
      if (
        obj &&
        typeof obj === 'object' &&
        obj.type === 'artifact' &&
        obj.artifact_type &&
        obj.data
      ) {
        return [
          {
            type: obj.artifact_type as ExtractedPart['type'],
            data: obj.data,
          },
        ];
      }
    } catch {
      // fall through
    }
  }

  const parts: ExtractedPart[] = [];
  let lastIndex = 0;

  // Try code blocks first
  const codeBlockRegex = /```(?:json)?\s*\n?([\s\S]*?)```/g;
  let cbMatch: RegExpExecArray | null;
  const codeBlockArtifacts: Array<{ start: number; end: number; part: ExtractedPart }> = [];

  while ((cbMatch = codeBlockRegex.exec(trimmed)) !== null) {
    const jsonStr = cbMatch[1].trim();
    if (jsonStr.startsWith('{') && jsonStr.endsWith('}')) {
      try {
        const obj = JSON.parse(jsonStr);
        if (
          obj &&
          typeof obj === 'object' &&
          obj.type === 'artifact' &&
          obj.artifact_type &&
          obj.data
        ) {
          codeBlockArtifacts.push({
            start: cbMatch.index,
            end: cbMatch.index + cbMatch[0].length,
            part: {
              type: obj.artifact_type as ExtractedPart['type'],
              data: obj.data,
            },
          });
        }
      } catch {
        // ignore
      }
    }
  }

  if (codeBlockArtifacts.length > 0) {
    for (const ca of codeBlockArtifacts) {
      if (ca.start > lastIndex) {
        const text = trimmed.slice(lastIndex, ca.start).trim();
        if (text) parts.push({ type: 'text', content: text });
      }
      parts.push(ca.part);
      lastIndex = ca.end;
    }
    if (lastIndex < trimmed.length) {
      const text = trimmed.slice(lastIndex).trim();
      if (text) parts.push({ type: 'text', content: text });
    }
    return parts;
  }

  // Inline JSON scan
  let i = 0;
  while (i < trimmed.length) {
    if (trimmed[i] === '{') {
      const end = findMatchingBraceEnd(trimmed, i);
      if (end !== -1) {
        const jsonStr = trimmed.slice(i, end + 1);
        try {
          const obj = JSON.parse(jsonStr);
          if (
            obj &&
            typeof obj === 'object' &&
            obj.type === 'artifact' &&
            obj.artifact_type &&
            obj.data
          ) {
            if (i > lastIndex) {
              const text = trimmed.slice(lastIndex, i).trim();
              if (text) parts.push({ type: 'text', content: text });
            }
            parts.push({
              type: obj.artifact_type as ExtractedPart['type'],
              data: obj.data,
            });
            lastIndex = end + 1;
            i = end + 1;
            continue;
          }
        } catch {
          // ignore
        }
      }
    }
    i++;
  }

  if (lastIndex < trimmed.length) {
    const text = trimmed.slice(lastIndex).trim();
    if (text) parts.push({ type: 'text', content: text });
  }

  return parts.length > 0 ? parts : [{ type: 'text', content: trimmed }];
}

/**
 * 统一的消息块提取器 - 识别所有特殊组件块
 */
export function extractAllSpecialBlocks(text: string): Array<{ type: 'text' | 'mermaid' | 'echarts' | 'map' | 'artifact'; content: string }> {
  // 识别 ```mermaid, ```echarts, ```map, ```artifact 块
  const blockRegex = /```(mermaid|echarts|map|artifact)\n([\s\S]*?)```/g;
  const parts: Array<{ type: 'text' | 'mermaid' | 'echarts' | 'map' | 'artifact'; content: string }> = [];
  
  let lastIndex = 0;
  let match;
  
  while ((match = blockRegex.exec(text)) !== null) {
    // 添加前面的文本
    if (match.index > lastIndex) {
      const prevText = text.slice(lastIndex, match.index);
      if (prevText.trim()) {
        parts.push({
          type: 'text',
          content: prevText,
        });
      }
    }
    
    // 添加特殊代码块
    parts.push({
      type: match[1] as any,
      content: match[2].trim(),
    });
    
    lastIndex = match.index + match[0].length;
  }
  
  // 添加剩余的文本
  if (lastIndex < text.length) {
    const remainingText = text.slice(lastIndex);
    if (remainingText.trim()) {
      parts.push({
        type: 'text',
        content: remainingText,
      });
    }
  }
  
  return parts.length > 0 ? parts : [{ type: 'text', content: text }];
}

