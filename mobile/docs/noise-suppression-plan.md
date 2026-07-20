# 移动端降噪方案

按住说话模式下，环境噪音和旁人人声导致 ASR 误识别、乱出字。本方案针对两个问题：

- **A 非人声噪音**（空调、风扇、马路、键盘）
- **B 旁人人声**（按住时旁边有人说话）

---

## 现状

| 平台 | VAD | 非人声降噪 | 旁人人声过滤 |
|------|-----|-----------|------------|
| iOS | ✅ Silero VAD | ❌ 未启用 | ❌ 无 |
| Android | ⚠️ 能量 VAD（无 Silero） | ❌ 未启用 | ❌ 无 |
| HarmonyOS | ❌ 无 VAD | ❌ 无 | ❌ 无 |

---

## 方案总览：能量门限 + 平台降噪

两层策略叠加，各平台共享上层逻辑、差异化底层实现：

```
麦克风 → 平台降噪（去非人声噪音） → 能量门限（过旁人人声） → ASR
```

---

## 第一层：能量门限（三平台统一）

**做法**：JS 层在 `onPartial` / `onFinal` 前加 RMS 能量判断。低于阈值的音频帧不送 ASR、不更新 UI。

### 为什么在第一层而不是 VAD？

VAD 判断"是否有人说话"，能量门限判断"是否够近/够大声"。按你说话自带近麦优势，用户音量天然 > 旁人，能量门限可以低成本过滤掉大部分旁人人声。

### JS 侧改动（`useVoiceInput.ts`）

新增配置参数：

```typescript
// JS 侧可调，默认 0.02（归一化 RMS）
energyThreshold: 0.02,
```

在 `start()` 时通过 `voiceEngine.setEnergyThreshold(val)` 下发到各平台原生侧。

### 各平台原生侧

| 平台 | 实现 |
|------|------|
| iOS | 已有 RMS 计算（`processAudioBuffer:` 内），加 `_energyThreshold` 比较，低于阈值跳过 ASR |
| Android | 已有 `calculateEnergy()`，加 `energyThreshold` 比较，逻辑同上 |
| HarmonyOS | 已有 `volume` 计算（`energy / 10000`），加 `energyThreshold` 比较 |

**成本**：每平台 ~10 行，无模型依赖。

---

## 第二层：非人声降噪（平台差异实现）

### Android — `NoiseSuppressor`

```kotlin
// RNCaptureVoiceStream.kt 或 RNVoiceEngineModule.kt
if (NoiseSuppressor.isAvailable()) {
    val ns = NoiseSuppressor.create(recorder.getAudioSessionId())
    ns.setEnabled(true)
}
```

依赖 `<uses-permission android:name="android.permission.RECORD_AUDIO" />`（已有）。

**成本**：1 行代码声卡级降噪。

### iOS — `AVAudioSession` 语音处理 Quality

```objc
// RNVoiceEngine.mm 246~248 行
AVAudioSession *session = [AVAudioSession sharedInstance];
[session setCategory:AVAudioSessionCategoryPlayAndRecord
         withOptions:AVAudioSessionCategoryOptionDefaultToSpeaker |
                     AVAudioSessionCategoryOptionAllowBluetooth
               error:nil];
// 添加：
[session setMode:AVAudioSessionModeVoiceChat error:nil];
```

`AVAudioSessionModeVoiceChat` 启用 Apple 内置的语音处理（降噪 + AEC），适用于单声道近麦输入。

**注意**：该模式会自动启用系统 AEC，与现有 `PlayAndRecord` 配合，TTS 播放时的回声也会被消除。

**成本**：改 1 行。

### HarmonyOS — GTCRN Denoiser

Sherpa-ONNX 已绑定 `OnlineSpeechDenoiser`（GTCRN 模型），未接入。需要：

1. **下载 GTCRN 模型**（`gtcrn.onnx`）放入应用资源目录
2. **创建 Denoiser**：`sherpa_onnx.createOnlineSpeechDenoiser(gtcrn.onnx)`
3. **音频管线接入**：`processAudioChunk()` 中，调用 `denoiser.process(samples)` 后再送 ASR

```typescript
// RNVoiceEngineTurboModule.ets（伪代码）
if (this.denoiser) {
    const denoised = this.denoiser.process(floatSamples);
    this.currentStream.acceptWaveform({ samples: denoised, sampleRate: this.sampleRate });
} else {
    this.currentStream.acceptWaveform({ samples: floatSamples, sampleRate: this.sampleRate });
}
```

**成本**：模型约 1~2MB，代码 ~30 行。

---

## 第三层：补 VAD

### HarmonyOS — 补 Silero VAD

iOS/Android 已有 VAD，HarmonyOS 缺失。最小成本补一个轻量级 VAD：

#### 方案 A（推荐）：使用 Sherpa-ONNX 已绑定的 Silero VAD

Sherpa-ONNX 提供了 `SileroVad` C API，`Vad.ets` 已有封装类，但 RNVoiceEngineTurboModule 没有使用。

接入到 `processAudioChunk()` 中：

```typescript
// 初始化时
const vadConfig = new VadConfig({
    sampleRate: 16000,
    threshold: 0.5,
    minSilenceDurationMs: 800,
});
this.vad = new Vad(vadConfig);

// processAudioChunk 中
this.vad.acceptWaveform(floatSamples);
if (this.vad.isDetected()) {
    if (!this.isSpeaking) {
        this.isSpeaking = true;
        this.ctx.rnInstance.emitDeviceEvent('voiceEngine:vadStart', null);
    }
    // 送 ASR
} else {
    if (this.isSpeaking) {
        this.isSpeaking = false;
        this.ctx.rnInstance.emitDeviceEvent('voiceEngine:vadEnd', null);
    }
}
```

#### 方案 B（更低成本）：能量门限 VAD

先以能量门限跑通，之后再换 Silero VAD。

**成本**：方案 A ~50 行（已有封装类），方案 B ~15 行。

### Android — 升级为 Silero VAD

当前 Android 用能量 VAD（`VAD_ENERGY_THRESHOLD = 500.0`），代码注释自称"先以音量阈值简单实现，后续可替换"。建议替换为 Sherpa-ONNX 的 Silero VAD JNI，与 iOS 对齐。

**成本**：中等，需要 JNI 绑定 Silero VAD 模型。

---

## 总工作量估算

| 项目 | 平台 | 代码量 | 难度 |
|------|------|--------|------|
| 能量门限 | 三平台 JS + 原生 | ~30 行 | ★☆☆ |
| `NoiseSuppressor` | Android | 1 行 | ★☆☆ |
| `AVAudioSessionModeVoiceChat` | iOS | 1 行 | ★☆☆ |
| GTCRN Denoiser 接入 | HarmonyOS | ~50 行 | ★★☆ |
| Silero VAD 补全 | HarmonyOS | ~50 行 | ★★☆ |
| Silero VAD 升级 | Android | ~80 行 | ★★★ |
| **合计** | | **~200 行** | |

---

## 建议执行顺序

1. **能量门限（三平台）**—— 最便宜，立竿见影，挡住大部分旁人人声
2. **Android `NoiseSuppressor` + iOS `VoiceChat`**——各 1 行，顺手
3. **HarmonyOS 补 Silero VAD**——让鸿蒙跟 iOS/Android 对齐
4. **HarmonyOS GTCRN Denoiser**——进一步净化音频
5. **Android 升级 Silero VAD**——可选优化

---

## 不做的事

- **声纹识别**：需要 enrollment + 模型推理，按住说话场景下能量门限已能解决大部分问题，声纹属于过度设计
- **波束成形**：需要多麦克风 + 硬件 SDK，非纯软件方案
- **WebRTC AEC**：AEC 消除的是喇叭回声，与环境噪音无关。iOS `VoiceChat` mode 已内置 AEC；Android/HarmonyOS 当前无 TTS 打断需求可不做

---

## 风险

- `AVAudioSessionModeVoiceChat` 可能改变现有 TTS 播放音质（电话音质处理），需测试
- GTCRN 模型 1~2MB 增加包体积，若对讲音质接受可跳过
- Android `NoiseSuppressor` 依赖声卡驱动，部分低端机型可能效果不佳
