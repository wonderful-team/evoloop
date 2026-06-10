import { TurboModule, TurboModuleContext } from '@rnoh/react-native-openharmony/ts';
import { RNLiveAudioStream } from '../codegen/generated/turboModules/RNLiveAudioStream';
import { audio } from '@kit.AudioKit';
import { util } from '@kit.ArkTS';
import { BusinessError } from '@kit.BasicServicesKit';

export class RNLiveAudioStreamTurboModule extends TurboModule implements RNLiveAudioStream.Spec {
  private capturer: audio.AudioCapturer | null = null;
  private isRecording: boolean = false;
  private base64Helper = new util.Base64Helper();
  private sampleRate: number = 16000;
  private channels: number = 1;
  private bitsPerSample: number = 16;
  private audioSource: number = 0; // MIC

  constructor(ctx: TurboModuleContext) {
    super(ctx);
  }

  public init(options: {
    sampleRate: number;
    channels: number;
    bitsPerSample: number;
    audioSource: number;
    bufferSize: number;
  }): void {
    console.info(`[RNLiveAudioStream] init with options: ${JSON.stringify(options)}`);
    this.sampleRate = options.sampleRate;
    this.channels = options.channels;
    this.bitsPerSample = options.bitsPerSample;
    this.audioSource = options.audioSource;

    try {
      // 1. Map options to AudioStreamInfo
      const streamInfo: audio.AudioStreamInfo = {
        samplingRate: this.sampleRate,
        channels: this.channels,
        sampleFormat: this.bitsPerSample === 8 ? audio.AudioSampleFormat.SAMPLE_FORMAT_U8 : audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
        encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW
      };

      // 2. Map options to AudioCapturerInfo
      let sourceType = audio.SourceType.SOURCE_TYPE_MIC;
      if (this.audioSource === 6) { // VOICE_RECOGNITION in Android
        sourceType = audio.SourceType.SOURCE_TYPE_VOICE_RECOGNITION;
      }

      const capturerInfo: audio.AudioCapturerInfo = {
        source: sourceType,
        capturerFlags: 0
      };

      const capturerOptions: audio.AudioCapturerOptions = {
        streamInfo: streamInfo,
        capturerInfo: capturerInfo
      };

      // 3. Create AudioCapturer instance
      if (this.capturer) {
        try {
          this.capturer.release();
        } catch (e) {
          // ignore
        }
        this.capturer = null;
      }

      this.capturer = audio.createAudioCapturerSync(capturerOptions);
      console.info(`[RNLiveAudioStream] AudioCapturer created successfully`);

      // 4. Setup readData callback
      this.capturer.on('readData', (buffer: ArrayBuffer) => {
        if (!this.isRecording) {
          return;
        }
        try {
          const uint8Array = new Uint8Array(buffer);
          const base64Str = this.base64Helper.encodeToStringSync(uint8Array);
          // Emit the 'data' event directly via the RNInstance
          this.ctx.rnInstance.emitDeviceEvent('data', base64Str);
        } catch (err) {
          console.error(`[RNLiveAudioStream] Error in readData callback: ${JSON.stringify(err)}`);
        }
      });

    } catch (err) {
      const error = err as BusinessError;
      console.error(`[RNLiveAudioStream] Failed to init: code=${error.code}, msg=${error.message}`);
      throw err;
    }
  }

  public start(): void {
    console.info(`[RNLiveAudioStream] start recording`);
    if (!this.capturer) {
      console.error(`[RNLiveAudioStream] capturer is null, cannot start`);
      return;
    }

    if (this.isRecording) {
      console.warn(`[RNLiveAudioStream] capturer is already recording`);
      return;
    }

    try {
      this.capturer.start((err) => {
        if (err) {
          console.error(`[RNLiveAudioStream] Failed to start capturer: ${JSON.stringify(err)}`);
          return;
        }
        this.isRecording = true;
        console.info(`[RNLiveAudioStream] capturer started successfully`);
      });
    } catch (err) {
      const error = err as BusinessError;
      console.error(`[RNLiveAudioStream] Exception in start: code=${error.code}, msg=${error.message}`);
    }
  }

  public stop(): void {
    console.info(`[RNLiveAudioStream] stop recording`);
    if (!this.capturer || !this.isRecording) {
      console.warn(`[RNLiveAudioStream] capturer is not recording`);
      return;
    }

    try {
      this.capturer.stop((err) => {
        if (err) {
          console.error(`[RNLiveAudioStream] Failed to stop capturer: ${JSON.stringify(err)}`);
          return;
        }
        this.isRecording = false;
        console.info(`[RNLiveAudioStream] capturer stopped successfully`);
      });
    } catch (err) {
      const error = err as BusinessError;
      console.error(`[RNLiveAudioStream] Exception in stop: code=${error.code}, msg=${error.message}`);
    }
  }
}
