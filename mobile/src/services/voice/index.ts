// 语音服务导出

export { AudioRecorder, getAudioRecorder } from './AudioRecorder';
export { voiceEngine } from './VoiceEngine';
export { parseLocalIntent } from './localNLU';
export type { LocalIntent, IntentAction, IntentObject } from './localNLU';
export { extractSegments } from './streamingSegmenter';
export { ttsRouter } from './TTSRouter';
export type { TTSMode } from './TTSRouter';
