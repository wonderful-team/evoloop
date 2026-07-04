// 语言感知流式断句器
// 将 LLM 流式输出的文本 buffer 按语义边界切分为可播放的 TTS 片段
// 支持中日韩（按字符长度）和欧美西文（按单词数）两条路径

import i18n from '@/locales';

export interface SegmenterConfig {
  /**
   * 首句最小单元：首字优先，尽快发声降低 TTFS。
   * CJK 默认 6 字，西文默认 3 词。
   */
  firstChunkMin?: number;
  /**
   * 后续句最小单元：保障语义完整性，避免虚词被单独播放。
   * CJK 默认 10 字，西文默认 6 词。
   */
  followChunkMin?: number;
}

function isCJKLanguage(): boolean {
  return /^(zh|ja|ko)/.test(i18n.language ?? 'zh');
}

/**
 * 计算文本的"有效长度"：CJK 按字符数，西文按单词数。
 */
function measureLength(text: string, cjk: boolean): number {
  if (cjk) return text.length;
  return text.trim().split(/\s+/).filter(Boolean).length;
}

// 从 i18n 读取正则（每次调用均从当前语言包取，响应语言切换）
function getHardEndRegex(): RegExp {
  const raw = i18n.t('voiceNLU.sentenceEndHard') as string || '[。！？!?\\n]';
  return new RegExp(raw, 'g');
}

function getSoftEndRegex(): RegExp {
  const raw = i18n.t('voiceNLU.sentenceEndSoft') as string || '[，,；;：:]';
  return new RegExp(raw, 'g');
}

function getConjunctionRegex(): RegExp {
  const raw = i18n.t('voiceNLU.clausalConjunctions') as string || '并且|但是|所以|然后';
  return new RegExp(`(${raw})`, 'i');
}

/**
 * 从流式文本 buffer 中提取可立即播放的完整语义片段。
 *
 * 切分优先级：
 * 1. 强标点（句号/问号/感叹号）→ 无最小长度限制，立即切分
 * 2. 软标点（逗号/分号）+ 语义完整度（最小字/词数 或 含连词）→ 切分
 * 3. 不满足条件 → 保留在 buffer 中等待更多内容
 *
 * @param buffer - 当前累积的待切分文本
 * @param isFirst - 是否为当前 AI 回复的第一个片段（降低门限，优先首声）
 * @param config - 可选覆盖最小长度配置
 * @returns [提取出的片段数组, 剩余未切分的 buffer]
 */
export function extractSegments(
  buffer: string,
  isFirst: boolean,
  config?: SegmenterConfig
): [string[], string] {
  const cjk = isCJKLanguage();
  const firstMin  = config?.firstChunkMin  ?? (cjk ? 2 : 3);
  const followMin = config?.followChunkMin ?? (cjk ? 8 : 6);
  const minLen = isFirst ? firstMin : followMin;

  const hardRe = getHardEndRegex();
  const softRe = getSoftEndRegex();
  const conjRe = getConjunctionRegex();

  const segments: string[] = [];
  let remaining = buffer;
  let found = true;

  while (found) {
    found = false;

    // ── 1. 强标点：优先，不限最小长度 ───────────────────────
    hardRe.lastIndex = 0;
    const hm = hardRe.exec(remaining);
    if (hm) {
      const candidate = remaining.slice(0, hm.index + 1).trim();
      // 至少 2 个有效单位（防止单个标点误切）
      if (measureLength(candidate, cjk) >= 2) {
        segments.push(candidate);
        remaining = remaining.slice(hm.index + 1);
        found = true;
        continue;
      }
    }

    // ── 2. 软标点：满足语义完整度才切 ──────────────────────
    softRe.lastIndex = 0;
    let sm = softRe.exec(remaining);
    while (sm) {
      const candidate = remaining.slice(0, sm.index).trim();
      const len = measureLength(candidate, cjk);
      const nextText = remaining.slice(sm.index + 1).trim();

      // 达到最小长度，或者后续的文本以连词开头（说明已经是个完整的短句）
      if (len >= minLen || conjRe.test(nextText)) {
        segments.push(candidate);
        remaining = remaining.slice(sm.index + 1);
        found = true;
        break;
      }
      // 软标点太短，继续往后找
      sm = softRe.exec(remaining);
    }
  }

  return [segments, remaining];
}
