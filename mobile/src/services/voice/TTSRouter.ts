// TTS 网络感知路由层
// 网络良好 → qwen3-tts-flash（云端，高音质）
// 弱网/离线 → Sherpa-ONNX Kokoro-multi-lang-v1_1（本地，< 100ms 首字）
// 切换对上层调用方（useStreamingTTS）完全透明

import NetInfo from '@react-native-community/netinfo';
import RNFS from 'react-native-fs';
import { voiceEngine } from './VoiceEngine';
import type { TTSOptions } from '@/hooks/useStreamingTTS';

export type TTSMode = 'cloud' | 'local';

// Kokoro 音色映射表：云端 voiceId → 本地 speakerId（Kokoro v1_1 编号）
const KOKORO_VOICE_MAP: Record<string, number> = {
  Cherry: 0,   // 中文女声 0（温柔）
  Serena: 2,   // 中文女声 2（成熟）
  default: 0,
};

// 英文音色（当系统语言为 en 时使用）
const KOKORO_EN_VOICE_ID = 50; // kokoro_en_50（女声）

class TTSRouterClass {
  private _mode: TTSMode = 'cloud';
  private _isOnline = true;

  constructor() {
    // 初始化时立即查询一次网络状态
    NetInfo.fetch().then(state => {
      this._isOnline = (state.isConnected && state.isInternetReachable) ?? false;
      this._mode = this._isOnline ? 'cloud' : 'local';
    });

    // 订阅后续网络变化
    NetInfo.addEventListener(state => {
      const online = (state.isConnected && state.isInternetReachable) ?? false;
      if (online !== this._isOnline) {
        this._isOnline = online;
        const newMode: TTSMode = online ? 'cloud' : 'local';
        if (newMode !== this._mode) {
          this._mode = newMode;
          console.log(`[TTSRouter] → ${this._mode} TTS (online=${online})`);
        }
      }
    });
  }

  getMode(): TTSMode {
    return this._mode;
  }

  /**
   * 本地 Kokoro TTS 合成并通过 VoiceEngine 播放（离线路径）。
   * 首字延迟 < 100ms（无网络调用，本地 ONNX 推理）。
   *
   * @param text - 要合成的文本
   * @param options - TTS 参数（emotion 在本地 TTS 暂不生效，speed 生效）
   */
  async synthesizeLocal(text: string, options: TTSOptions): Promise<void> {
    if (!text.trim()) return;

    // 确定 Kokoro speakerId（根据云端 voiceId 映射）
    const voiceId = options.voiceId ?? 'Cherry';
    const speakerId = KOKORO_VOICE_MAP[voiceId] ?? KOKORO_VOICE_MAP.default;
    const speed = options.speed ?? 1.0;

    // 调用原生 Sherpa-ONNX OfflineTts 合成，返回本地 wav 文件路径
    // synthesizeTTS 由各平台原生层实现（iOS/Android/鸿蒙）
    const wavPath: string = await (voiceEngine as any).synthesizeTTS(
      text,
      speakerId,
      speed
    );

    if (!wavPath) {
      throw new Error('[TTSRouter] synthesizeTTS returned empty path');
    }

    // 读取为 base64 后通过现有 AudioRenderer 播放
    const base64 = await RNFS.readFile(wavPath, 'base64');
    // Kokoro 输出采样率为 22050Hz，单声道
    await voiceEngine.startAudioStream('wav', 22050);
    await voiceEngine.writeAudioChunk(base64);

    // 清理临时文件
    RNFS.unlink(wavPath).catch(() => {});
  }
}

export const ttsRouter = new TTSRouterClass();
