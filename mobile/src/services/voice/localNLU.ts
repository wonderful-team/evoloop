// 本地意图解析引擎（i18n 驱动）
// 无网络依赖，ASR onFinal 后第一时间拦截本地控制指令
// 命中则直接执行 UI 动作（< 30ms），不转发给云端大模型

import i18n from '@/locales';

export type IntentAction = 'OPEN' | 'CLOSE' | 'RESET' | 'MUTE' | 'UNMUTE' | null;
export type IntentObject = 'HISTORY' | 'AUDIO' | null;

export interface LocalIntent {
  action: IntentAction;
  object: IntentObject;
  rawText: string;
}

// 按语言缓存编译后的 RegExp，避免 onFinal 热路径上重复 compile
let cachedLang = '';
let cachedPatterns: Record<string, RegExp> = {};

function getPattern(key: string): RegExp {
  const lang = i18n.language ?? 'zh';
  if (lang !== cachedLang) {
    // 语言切换时清空缓存，重新编译新语言的 RegExp
    cachedLang = lang;
    cachedPatterns = {};
  }
  if (!cachedPatterns[key]) {
    const raw = i18n.t(`voiceNLU.${key}`) as string;
    if (!raw) {
      // 回退：返回不可能匹配的 pattern
      cachedPatterns[key] = /(?!)/;
      return cachedPatterns[key];
    }
    // 中日韩：无词边界，直接用原始 pattern
    // 欧美西文：加 \b 词边界，防止 "open" 误匹配 "reopen"
    const isCJK = /^(zh|ja|ko)/.test(lang);
    const pattern = isCJK
      ? raw
      : raw.split('|').map(w => `\\b${w.trim()}\\b`).join('|');
    cachedPatterns[key] = new RegExp(pattern, 'i');
  }
  return cachedPatterns[key];
}

/**
 * 解析 ASR 识别出的文本，判断是否为本地可直接执行的控制指令。
 *
 * @param text - ASR 的最终识别文本
 * @param uiState - 当前 UI 状态（用于指代消解）
 * @returns 匹配到的意图（含 action + object），或 null（表示应转发给云端 LLM）
 *
 * @example
 * parseLocalIntent('把历史抽屉打开', { isHistoryOpen: false })
 * // => { action: 'OPEN', object: 'HISTORY', rawText: '把历史抽屉打开' }
 *
 * parseLocalIntent('今天天气怎么样', { isHistoryOpen: false })
 * // => null  （转给 LLM）
 */
export function parseLocalIntent(
  text: string,
  uiState: { isHistoryOpen: boolean }
): LocalIntent | null {
  const t = text.trim().toLowerCase();

  let action: IntentAction = null;
  let object: IntentObject = null;

  // ── 动作识别（优先级从高到低，避免歧义覆盖）──────────────
  if (getPattern('actMute').test(t))        action = 'MUTE';
  else if (getPattern('actUnmute').test(t)) action = 'UNMUTE';
  else if (getPattern('actOpen').test(t))   action = 'OPEN';
  else if (getPattern('actClose').test(t))  action = 'CLOSE';
  else if (getPattern('actReset').test(t))  action = 'RESET';

  // 无法识别动作 → 不是本地指令，交云端处理
  if (!action) return null;

  // ── 对象识别 ─────────────────────────────────────────────
  if (getPattern('objHistory').test(t))    object = 'HISTORY';
  else if (getPattern('objAudio').test(t)) object = 'AUDIO';
  else if (getPattern('pronouns').test(t)) {
    // 指代消解：结合当前 UI 状态推断指代对象
    if (uiState.isHistoryOpen) object = 'HISTORY';
  }

  // MUTE / UNMUTE 不需要显式 object，直接作用于 AUDIO
  if (action === 'MUTE' || action === 'UNMUTE') {
    return { action, object: 'AUDIO', rawText: text };
  }

  // 其余 action 必须有 object 才构成合法本地指令
  if (!object) return null;

  return { action, object, rawText: text };
}
