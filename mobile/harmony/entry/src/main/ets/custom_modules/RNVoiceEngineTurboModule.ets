import { TurboModule, TurboModuleContext } from '@rnoh/react-native-openharmony/ts';
import { RNVoiceEngine } from '../codegen/generated/turboModules/RNVoiceEngine';
import { audio } from '@kit.AudioKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { util } from '@kit.ArkTS';
import fs from '@ohos.file.fs';
import {
  OfflineTts,
  OfflineTtsConfig,
  TtsInput,
  OnlineModelConfig,
  OnlineRecognizer,
  OnlineRecognizerConfig,
  OnlineStream,
} from 'sherpa_onnx';
import resourceManager from '@ohos.resourceManager';

function writeWavHeader(samplesCount: number, sampleRate: number): Uint8Array {
  const header = new Uint8Array(44);
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x52494646, false); // "RIFF"
  view.setUint32(4, 36 + samplesCount * 2, true);
  view.setUint32(8, 0x57415645, false); // "WAVE"
  view.setUint32(12, 0x666d7420, false); // "fmt "
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM = 1
  view.setUint16(22, 1, true); // Mono = 1
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  view.setUint32(36, 0x64617461, false); // "data"
  view.setUint32(40, samplesCount * 2, true);
  return header;
}

function float32ToInt16(samples: Float32Array): Int16Array {
  const int16 = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    let s = Math.max(-1, Math.min(1, samples[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return int16;
}

function existsSync(path: string): boolean {
  try {
    return fs.accessSync(path);
  } catch (err) {
    return false;
  }
}

function copyRawFileOrFolder(mgr: resourceManager.ResourceManager, srcPath: string, destDir: string): void {
  try {
    let list: string[] = [];
    try {
      list = mgr.getRawFileListSync(srcPath);
    } catch (e) {
      // Ignored
    }

    if (list && list.length > 0) {
      const newDestDir = `${destDir}/${srcPath}`;
      if (!existsSync(newDestDir)) {
        fs.mkdirSync(newDestDir);
      }
      for (let i = 0; i < list.length; i++) {
        const item = list[i];
        const nextSrc = srcPath ? `${srcPath}/${item}` : item;
        copyRawFileOrFolder(mgr, nextSrc, destDir);
      }
    } else {
      const destPath = `${destDir}/${srcPath}`;
      const parentDir = destPath.substring(0, destPath.lastIndexOf('/'));
      if (!existsSync(parentDir)) {
        const parts = srcPath.split('/');
        let currentSubDir = destDir;
        for (let i = 0; i < parts.length - 1; i++) {
          currentSubDir = `${currentSubDir}/${parts[i]}`;
          if (!existsSync(currentSubDir)) {
            fs.mkdirSync(currentSubDir);
          }
        }
      }
      if (existsSync(destPath)) {
        let size = 0;
        try {
          const stat = fs.statSync(destPath);
          size = stat.size;
        } catch (e) {}
        if (size > 0) {
          return;
        }
      }
      const content = mgr.getRawFileContentSync(srcPath);
      const file = fs.openSync(destPath, fs.OpenMode.CREATE | fs.OpenMode.WRITE_ONLY);
      fs.writeSync(file.fd, content.buffer);
      fs.closeSync(file);
    }
  } catch (err) {
    console.error(`Failed to copy rawfile ${srcPath}: ${JSON.stringify(err)}`);
  }
}

interface InitializeConfig {
  modelDir: string;
  sampleRate?: number;
  numThreads?: number;
  vadThreshold?: number;
  energyThreshold?: number;
  silenceTimeoutMs?: number;
}

interface AudioStreamConfig {
  sampleRate?: number;
  channels?: number;
  format: string;
}

interface SynthesizeParams {
  text: string;
  speakerId: number;
  speed: number;
}

export class RNVoiceEngineTurboModule extends TurboModule implements RNVoiceEngine.Spec {
  private capturer: audio.AudioCapturer | null = null;
  private isRecording: boolean = false;
  private sampleRate: number = 16000;
  private energyThreshold: number = 0.02;
  private accumulatedBuffer: Int16Array = new Int16Array(0);

  // Sherpa-ONNX ASR (running on main thread; Workers cannot load native modules)
  private recognizer: OnlineRecognizer | null = null;
  private currentStream: OnlineStream | null = null;

  // Audio renderer for TTS
  private renderer: audio.AudioRenderer | null = null;
  private base64Helper = new util.Base64Helper();

  constructor(ctx: TurboModuleContext) {
    super(ctx);
  }

  // NativeEventEmitter 在 Bridgeless/TurboModule 模式下要求存在这两个方法
  public addListener(eventName: string): void {
    console.info(`[RNVoiceEngine] addListener: ${eventName}`);
  }

  public removeListeners(count: number): void {
    console.info(`[RNVoiceEngine] removeListeners: ${count}`);
  }

  private offlineTts: OfflineTts | null = null;

  private getOrInitTTS(): OfflineTts | null {
    if (this.offlineTts) {
      return this.offlineTts;
    }
    try {
      const config = new OfflineTtsConfig();
      config.model.kokoro.model = 'sherpa-kokoro/model.onnx';
      config.model.kokoro.voices = 'sherpa-kokoro/voices.bin';
      config.model.kokoro.tokens = 'sherpa-kokoro/tokens.txt';
      config.model.kokoro.dataDir = 'sherpa-kokoro/espeak-ng-data';
      config.model.kokoro.lexicon = 'sherpa-kokoro/lexicon-zh.txt';
      config.model.kokoro.lengthScale = 1.0;
      config.model.numThreads = 2;
      config.model.provider = 'cpu';

      const resourceManager = this.ctx.uiAbilityContext.resourceManager;
      this.offlineTts = new OfflineTts(config, resourceManager);
      console.info('[RNVoiceEngine] Offline Kokoro TTS initialized successfully on HarmonyOS');
    } catch (err) {
      console.error(`[RNVoiceEngine] Failed to initialize Offline Kokoro TTS: ${JSON.stringify(err)}`);
    }
    return this.offlineTts;
  }

  public initialize(config: InitializeConfig): Promise<void> {
    console.info('[RNVoiceEngine] initialize on HarmonyOS (Sherpa-ONNX local ASR on main thread)');
    this.sampleRate = config.sampleRate ?? 16000;
    this.energyThreshold = config.energyThreshold ?? 0.02;

    return new Promise((resolve, reject) => {
      try {
        let modelDir = config.modelDir || 'sherpa-onnx-streaming-zipformer-zh-14M-2023-02-23';
        if (modelDir.startsWith('sherpa-asr/')) {
          modelDir = modelDir.substring('sherpa-asr/'.length);
        }

        // Copy files from rawfile to filesDir so that native code can open them via filesystem
        const filesDir = this.ctx.uiAbilityContext.filesDir;
        const resourceManager = this.ctx.uiAbilityContext.resourceManager;
        console.info(`[RNVoiceEngine] copying ASR models from rawfile to ${filesDir}...`);
        copyRawFileOrFolder(resourceManager, modelDir, filesDir);
        const absoluteModelDir = `${filesDir}/${modelDir}`;
        console.info(`[RNVoiceEngine] ASR models copied, absolute path: ${absoluteModelDir}`);

        // Verify model files exist before creating recognizer
        const requiredFiles = [
          `${absoluteModelDir}/encoder-epoch-99-avg-1.int8.onnx`,
          `${absoluteModelDir}/decoder-epoch-99-avg-1.onnx`,
          `${absoluteModelDir}/joiner-epoch-99-avg-1.int8.onnx`,
          `${absoluteModelDir}/tokens.txt`,
        ];
        for (const file of requiredFiles) {
          const fileExists = existsSync(file);
          console.info(`[RNVoiceEngine] model file ${file}: ${fileExists ? 'exists' : 'MISSING'}`);
        }

        const modelConfig = new OnlineModelConfig();
        modelConfig.transducer.encoder = `${absoluteModelDir}/encoder-epoch-99-avg-1.int8.onnx`;
        modelConfig.transducer.decoder = `${absoluteModelDir}/decoder-epoch-99-avg-1.onnx`;
        modelConfig.transducer.joiner = `${absoluteModelDir}/joiner-epoch-99-avg-1.int8.onnx`;
        modelConfig.tokens = `${absoluteModelDir}/tokens.txt`;
        modelConfig.modelType = 'zipformer';
        modelConfig.numThreads = config.numThreads ?? 2;

        const recognizerConfig = new OnlineRecognizerConfig();
        recognizerConfig.modelConfig = modelConfig;
        recognizerConfig.enableEndpoint = true;
        recognizerConfig.rule1MinTrailingSilence = (config.silenceTimeoutMs ?? 800) / 1000;
        recognizerConfig.rule2MinTrailingSilence = (config.silenceTimeoutMs ?? 800) / 1000;
        recognizerConfig.rule3MinUtteranceLength = 20.0;

        this.recognizer = new OnlineRecognizer(recognizerConfig);
        this.currentStream = this.recognizer.createStream();
        console.info('[RNVoiceEngine] ASR recognizer initialized on main thread');
        resolve();
      } catch (err) {
        const errStr = err instanceof Error ? err.message : String(err);
        console.error(`[RNVoiceEngine] initialize failed: ${errStr}`);
        console.error(`[RNVoiceEngine] initialize failed raw: ${JSON.stringify(err)}`);
        reject(new Error(`Initialize failed: ${errStr}`));
      }
    });
  }

  public setMode(mode: string): Promise<void> {
    console.info(`[RNVoiceEngine] setMode: ${mode}`);
    return Promise.resolve();
  }

  public start(): Promise<void> {
    return new Promise((resolve, reject) => {
      console.info('[RNVoiceEngine] start called');
      if (this.isRecording) {
        console.info('[RNVoiceEngine] already recording');
        resolve();
        return;
      }

      if (!this.recognizer) {
        console.error('[RNVoiceEngine] ASR recognizer not initialized');
        reject(new Error('ASR recognizer not initialized'));
        return;
      }

      try {
        this.currentStream = this.recognizer.createStream();
        console.info('[RNVoiceEngine] Fresh ASR stream created for new session');
      } catch (streamErr) {
        console.error(`[RNVoiceEngine] Failed to create fresh stream: ${JSON.stringify(streamErr)}`);
      }

      this.accumulatedBuffer = new Int16Array(0);

      const streamInfo: audio.AudioStreamInfo = {
        samplingRate: this.sampleRate,
        channels: 1,
        sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW,
      };

      const capturerInfo: audio.AudioCapturerInfo = {
        source: audio.SourceType.SOURCE_TYPE_VOICE_RECOGNITION,
        capturerFlags: 0,
      };

      const capturerOptions: audio.AudioCapturerOptions = {
        streamInfo: streamInfo,
        capturerInfo: capturerInfo,
      };

      if (this.capturer) {
        try {
          this.capturer.off('readData');
          this.capturer.release();
        } catch {}
        this.capturer = null;
      }

      console.info('[RNVoiceEngine] creating audio capturer...');
      audio.createAudioCapturer(capturerOptions).then((capturer) => {
        console.info('[RNVoiceEngine] audio capturer created');
        this.capturer = capturer;

        this.capturer.on('readData', (buffer: ArrayBuffer) => {
          if (!this.isRecording) {
            return;
          }
          try {
            const uint8Array = new Uint8Array(buffer);
            const samplesCount = Math.floor(uint8Array.length / 2);
            const int16Array = new Int16Array(samplesCount);
            const view = new DataView(uint8Array.buffer, uint8Array.byteOffset, uint8Array.byteLength);
            for (let i = 0; i < samplesCount; i++) {
              int16Array[i] = view.getInt16(i * 2, true);
            }
            this.processAudioChunk(int16Array);
          } catch (err) {
            console.error(`[RNVoiceEngine] readData error: ${JSON.stringify(err)}`);
          }
        });

        console.info('[RNVoiceEngine] starting capturer...');
        this.capturer.start((err) => {
          if (err) {
            console.error(`[RNVoiceEngine] capturer start failed: ${JSON.stringify(err)}`);
            reject(new Error(`Failed to start capturer: ${JSON.stringify(err)}`));
            return;
          }
          this.isRecording = true;
          this.ctx.rnInstance.emitDeviceEvent('voiceEngine:vadStart', null);
          console.info('[RNVoiceEngine] capturer started');
          resolve();
        });
      }).catch((err: BusinessError) => {
        console.error(`[RNVoiceEngine] create capturer failed: ${JSON.stringify(err)}`);
        reject(new Error(`Failed to create capturer: ${JSON.stringify(err)}`));
      });
    });
  }

  private processAudioChunk(int16Array: Int16Array): void {
    if (!this.recognizer || !this.currentStream) {
      return;
    }

    const temp = new Int16Array(this.accumulatedBuffer.length + int16Array.length);
    temp.set(this.accumulatedBuffer, 0);
    temp.set(int16Array, this.accumulatedBuffer.length);
    this.accumulatedBuffer = temp;

    const chunkSize = 3200; // ~100ms at 16kHz 16bit mono
    while (this.accumulatedBuffer.length >= chunkSize) {
      const chunk = this.accumulatedBuffer.slice(0, chunkSize);
      this.accumulatedBuffer = this.accumulatedBuffer.slice(chunkSize);

      // 计算音量
      let energy = 0;
      for (let i = 0; i < chunk.length; i++) {
        energy += chunk[i] * chunk[i];
      }
      energy = Math.sqrt(energy / chunk.length);
      const volume = Math.min(1, energy / 10000);
      this.ctx.rnInstance.emitDeviceEvent('voiceEngine:volume', { value: volume });

      // 能量门限：过低则跳过 ASR（过滤噪音底噪）
      if ((energy / 32768.0) < this.energyThreshold) {
        continue;
      }

      // 转 Float32Array 送入 recognizer
      const floatSamples = new Float32Array(chunk.length);
      for (let i = 0; i < chunk.length; i++) {
        floatSamples[i] = chunk[i] / 32768.0;
      }

      this.currentStream.acceptWaveform({ samples: floatSamples, sampleRate: this.sampleRate });

      while (this.recognizer.isReady(this.currentStream)) {
        this.recognizer.decode(this.currentStream);
      }

      const result = this.recognizer.getResult(this.currentStream);
      if (result.text && result.text.trim() !== '') {
        this.ctx.rnInstance.emitDeviceEvent('voiceEngine:partial', { text: result.text.trim() });
      }

      if (this.recognizer.isEndpoint(this.currentStream)) {
        const finalText = result.text;
        if (finalText && finalText.trim() !== '') {
          this.ctx.rnInstance.emitDeviceEvent('voiceEngine:final', { text: finalText.trim() });
        }
        this.recognizer.reset(this.currentStream);
      }
    }
  }

  public stop(): Promise<void> {
    return new Promise((resolve) => {
      this.isRecording = false;
      if (!this.capturer) {
        resolve();
        return;
      }
      this.capturer.stop((err) => {
        if (err) {
          console.error(`[RNVoiceEngine] stop error: ${JSON.stringify(err)}`);
        }

        // Process any remaining samples in accumulatedBuffer before clearing it
        try {
          if (this.recognizer && this.currentStream) {
            if (this.accumulatedBuffer && this.accumulatedBuffer.length > 0) {
              const floatSamples = new Float32Array(this.accumulatedBuffer.length);
              for (let i = 0; i < this.accumulatedBuffer.length; i++) {
                floatSamples[i] = this.accumulatedBuffer[i] / 32768.0;
              }
              this.currentStream.acceptWaveform({ samples: floatSamples, sampleRate: this.sampleRate });
            }

            // Tell the stream that input is finished
            this.currentStream.inputFinished();

            // Decode remaining features
            while (this.recognizer.isReady(this.currentStream)) {
              this.recognizer.decode(this.currentStream);
            }

            // Get final results and emit the event
            const result = this.recognizer.getResult(this.currentStream);
            if (result && result.text && result.text.trim() !== '') {
              console.info(`[RNVoiceEngine] emitting final event on manual stop: ${result.text.trim()}`);
              this.ctx.rnInstance.emitDeviceEvent('voiceEngine:final', { text: result.text.trim() });
            }
          }
        } catch (asrErr) {
          console.error(`[RNVoiceEngine] Error flushing final ASR on stop: ${JSON.stringify(asrErr)}`);
        }

        this.accumulatedBuffer = new Int16Array(0);
        this.ctx.rnInstance.emitDeviceEvent('voiceEngine:vadEnd', null);
        resolve();
      });
    });
  }

  public release(): Promise<void> {
    return new Promise((resolve) => {
      this.isRecording = false;
      if (this.capturer) {
        try {
          this.capturer.off('readData');
          this.capturer.release();
        } catch {}
        this.capturer = null;
      }
      this.currentStream = null;
      this.recognizer = null;
      if (this.renderer) {
        try {
          this.renderer.stop();
          this.renderer.release();
        } catch {}
        this.renderer = null;
      }
      if (this.offlineTts) {
        this.offlineTts = null;
      }
      resolve();
    });
  }

  // === TTS Audio ===
  public playAudioStream(config: AudioStreamConfig): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.renderer) {
        try {
          this.renderer.stop();
          this.renderer.release();
        } catch {}
      }

      const streamInfo: audio.AudioStreamInfo = {
        samplingRate: config.sampleRate ?? 24000,
        channels: config.channels ?? 1,
        sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW,
      };

      const rendererInfo: audio.AudioRendererInfo = {
        usage: audio.StreamUsage.STREAM_USAGE_MEDIA,
        rendererFlags: 0,
      };

      const rendererOptions: audio.AudioRendererOptions = {
        streamInfo: streamInfo,
        rendererInfo: rendererInfo,
      };

      audio.createAudioRenderer(rendererOptions).then((renderer) => {
        this.renderer = renderer;
        this.renderer.start((err) => {
          if (err) {
            reject(new Error(`Failed to start renderer: ${JSON.stringify(err)}`));
            return;
          }
          resolve();
        });
      }).catch((err: BusinessError) => {
        reject(new Error(`Failed to create renderer: ${JSON.stringify(err)}`));
      });
    });
  }

  public writeAudioChunk(base64Data: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (!this.renderer) {
        reject(new Error('Renderer not initialized'));
        return;
      }
      try {
        const decoded = this.base64Helper.decodeSync(base64Data);
        const uint8Array = new Uint8Array(decoded);
        const pcmOffset = uint8Array.length > 44 &&
          uint8Array[0] === 0x52 && uint8Array[1] === 0x49 && uint8Array[2] === 0x46 && uint8Array[3] === 0x46
          ? 44
          : 0;
        const pcmData = uint8Array.slice(pcmOffset);
        this.renderer.write(pcmData.buffer as ArrayBuffer).then(() => {
          resolve();
        }).catch((err: BusinessError) => {
          reject(new Error(`Write failed: ${JSON.stringify(err)}`));
        });
      } catch (err) {
        reject(new Error(`Decode failed: ${JSON.stringify(err)}`));
      }
    });
  }

  public stopAudio(): Promise<void> {
    return new Promise((resolve) => {
      if (this.renderer) {
        try {
          this.renderer.stop();
          this.renderer.release();
        } catch {}
        this.renderer = null;
      }
      resolve();
    });
  }

  public setVadThreshold(value: number): Promise<void> {
    console.info(`[RNVoiceEngine] setVadThreshold: ${value}`);
    return Promise.resolve();
  }

  public synthesizeTTS(params: SynthesizeParams): Promise<string> {
    return new Promise((resolve, reject) => {
      const text = params.text;
      const speakerId = params.speakerId ?? 0;
      const speed = params.speed ?? 1.0;

      if (!text) {
        resolve('');
        return;
      }

      try {
        const tts = this.getOrInitTTS();
        if (!tts) {
          reject(new Error('TTS engine not initialized'));
          return;
        }

        const input = new TtsInput();
        input.text = text;
        input.sid = speakerId;
        input.speed = speed;

        const output = tts.generate(input);
        if (!output || !output.samples || output.samples.length === 0) {
          reject(new Error('Failed to generate audio samples'));
          return;
        }

        const tempDir = this.ctx.uiAbilityContext.tempDir;
        const fileName = `tts_${Date.now()}_${Math.floor(Math.random() * 1000)}.wav`;
        const filePath = `${tempDir}/${fileName}`;

        const file = fs.openSync(filePath, fs.OpenMode.CREATE | fs.OpenMode.READ_WRITE);
        const header = writeWavHeader(output.samples.length, output.sampleRate);
        const int16Samples = float32ToInt16(output.samples);

        fs.writeSync(file.fd, header.buffer);
        fs.writeSync(file.fd, int16Samples.buffer);
        fs.closeSync(file);

        resolve(filePath);
      } catch (err) {
        console.error(`[RNVoiceEngine] synthesizeTTS error: ${JSON.stringify(err)}`);
        reject(new Error(`TTS synthesis failed: ${JSON.stringify(err)}`));
      }
    });
  }
}
