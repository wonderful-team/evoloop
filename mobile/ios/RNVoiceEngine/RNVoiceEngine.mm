//
//  RNVoiceEngine.mm
//  EvoLoopMobile
//

#import "RNVoiceEngine.h"
#import <AVFoundation/AVFoundation.h>
#include <string>
#include <vector>
#include <math.h>
#include "sherpa-onnx/c-api/c-api.h"

class BiquadFilter {
  float b0, b1, b2, a1, a2;
  float x1, x2, y1, y2;
public:
  BiquadFilter() {
    double w0 = 2.0 * M_PI * 170.0 / 16000.0;
    double alpha = sin(w0) / (2.0 * 0.94);
    
    double b0_d = alpha;
    double b1_d = 0.0;
    double b2_d = -alpha;
    double a0_d = 1.0 + alpha;
    double a1_d = -2.0 * cos(w0);
    double a2_d = 1.0 - alpha;
    
    b0 = (float)(b0_d / a0_d);
    b1 = (float)(b1_d / a0_d);
    b2 = (float)(b2_d / a0_d);
    a1 = (float)(a1_d / a0_d);
    a2 = (float)(a2_d / a0_d);
    
    x1 = x2 = y1 = y2 = 0.0f;
  }
  
  float process(float x) {
    float y = b0*x + b1*x1 + b2*x2 - a1*y1 - a2*y2;
    x2 = x1;
    x1 = x;
    y2 = y1;
    y1 = y;
    return y;
  }
  
  void reset() {
    x1 = x2 = y1 = y2 = 0.0f;
  }
};

@interface RNVoiceEngine () <AVAudioPlayerDelegate> {
  const SherpaOnnxOnlineRecognizer *_recognizer;
  const SherpaOnnxOnlineStream *_stream;
  const SherpaOnnxVoiceActivityDetector *_vad;
  AVAudioEngine *_audioEngine;
  AVAudioConverter *_audioConverter;
  BOOL _isRunning;
  BOOL _isRecognizing;
  std::string _lastText;
  std::vector<std::string> _stringHolders;
  NSMutableArray<NSString *> *_partialBuffer;
  NSTimer *_vadEndTimer;

  // Audio player for TTS
  AVAudioPlayer *_audioPlayer;
  NSMutableData *_audioBuffer;

  const SherpaOnnxOfflineTts *_tts;
  BiquadFilter _pitchFilter;
  float _vadThreshold;
  int _silenceTimeoutMs;
}
@end

@implementation RNVoiceEngine

RCT_EXPORT_MODULE(RNVoiceEngine);

+ (BOOL)requiresMainQueueSetup {
  return YES;
}

- (NSArray<NSString *> *)supportedEvents {
  return @[
    @"voiceEngine:vadStart",
    @"voiceEngine:vadEnd",
    @"voiceEngine:partial",
    @"voiceEngine:final",
    @"voiceEngine:volume",
    @"voiceEngine:error",
    @"audio:ended",
    @"audio:error"
  ];
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _recognizer = NULL;
    _stream = NULL;
    _vad = NULL;
    _tts = NULL;
    _audioEngine = nil;
    _isRunning = NO;
    _isRecognizing = NO;
    _partialBuffer = [NSMutableArray array];
    _audioBuffer = [NSMutableData data];
    _vadThreshold = 0.5f;
    _silenceTimeoutMs = 800;
  }
  return self;
}

- (void)dealloc {
  [self releaseInternal];
}

#pragma mark - ASR Lifecycle

RCT_EXPORT_METHOD(initialize:(NSDictionary *)config
                  resolve:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  [self releaseInternal];
  _stringHolders.clear();
  _lastText = "";
  [_partialBuffer removeAllObjects];
  [_audioBuffer setLength:0];

  @try {
    NSString *modelDir = config[@"modelDir"] ?: @"";
    int numThreads = config[@"numThreads"] != nil ? [config[@"numThreads"] intValue] : 2;
    float vadThreshold = config[@"vadThreshold"] != nil ? [config[@"vadThreshold"] floatValue] : 0.5f;
    int silenceTimeoutMs = config[@"silenceTimeoutMs"] != nil ? [config[@"silenceTimeoutMs"] intValue] : 800;

    NSBundle *bundle = [NSBundle mainBundle];

    auto resolvePath = ^NSString *(NSString *resource, NSString *ext) {
      NSString *path = [bundle pathForResource:resource ofType:ext inDirectory:modelDir];
      if (!path) path = [bundle pathForResource:resource ofType:ext inDirectory:@"sherpa-asr"];
      if (!path) path = [bundle pathForResource:resource ofType:ext];
      return path;
    };

    NSString *encoderPath = resolvePath(@"encoder-epoch-99-avg-1.int8", @"onnx");
    NSString *decoderPath = resolvePath(@"decoder-epoch-99-avg-1.int8", @"onnx");
    NSString *joinerPath = resolvePath(@"joiner-epoch-99-avg-1.int8", @"onnx");
    NSString *tokensPath = resolvePath(@"tokens", @"txt");

    if (!encoderPath || !decoderPath || !joinerPath || !tokensPath) {
      reject(@"INIT_ERROR", @"Model files not found in bundle", nil);
      return;
    }

    auto hold = [self](NSString *str) -> const char * {
      _stringHolders.push_back(std::string(str.UTF8String));
      return _stringHolders.back().c_str();
    };

    SherpaOnnxOnlineTransducerModelConfig transducerConfig = {
      .encoder = hold(encoderPath),
      .decoder = hold(decoderPath),
      .joiner = hold(joinerPath),
    };

    SherpaOnnxOnlineModelConfig modelConfig = {};
    modelConfig.transducer = transducerConfig;
    modelConfig.tokens = hold(tokensPath);
    modelConfig.num_threads = numThreads;
    modelConfig.provider = hold(@"cpu");
    modelConfig.model_type = hold(@"zipformer");

    SherpaOnnxFeatureConfig featConfig = { .sample_rate = 16000, .feature_dim = 80 };

    SherpaOnnxOnlineRecognizerConfig recConfig = {};
    recConfig.feat_config = featConfig;
    recConfig.model_config = modelConfig;
    recConfig.decoding_method = hold(@"greedy_search");
    recConfig.max_active_paths = 4;

    _recognizer = SherpaOnnxCreateOnlineRecognizer(&recConfig);
    if (!_recognizer) {
      reject(@"INIT_ERROR", @"Failed to create OnlineRecognizer", nil);
      return;
    }

    // VAD config: 30ms window, silence timeout 800ms
    int32_t vadWindowSize = 512;  // samples at 16kHz ~= 32ms
    float vadSilenceThreshold = 0.04f;
    _vadThreshold = vadThreshold;
    _silenceTimeoutMs = silenceTimeoutMs;

    NSString *vadModelPath = [bundle pathForResource:@"silero_vad" ofType:@"onnx" inDirectory:@"sherpa-vad"];
    if (!vadModelPath) vadModelPath = [bundle pathForResource:@"silero_vad" ofType:@"onnx"];

    if (vadModelPath) {
      SherpaOnnxVadModelConfig vadModelConfig = {};
      vadModelConfig.silero_vad.model = hold(vadModelPath);
      vadModelConfig.silero_vad.threshold = vadThreshold;
      vadModelConfig.silero_vad.min_silence_duration = (float)silenceTimeoutMs / 1000.0f;
      vadModelConfig.silero_vad.min_speech_duration = 0.25f;
      vadModelConfig.sample_rate = 16000;
      vadModelConfig.num_threads = 1;

      _vad = SherpaOnnxCreateVoiceActivityDetector(&vadModelConfig, vadWindowSize);
    }

    if (!_vad) {
      NSLog(@"[RNVoiceEngine] VAD not available (model not found), continuing without VAD");
    }

    NSLog(@"[RNVoiceEngine] Initialized");
    resolve(nil);
  } @catch (NSException *exception) {
    reject(@"INIT_ERROR", exception.reason, nil);
  }
}

RCT_EXPORT_METHOD(setMode:(NSString *)mode
                  resolve:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  _isRecognizing = [mode isEqualToString:@"asr"];
  resolve(nil);
}

RCT_EXPORT_METHOD(start:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  if (_isRunning) {
    resolve(nil);
    return;
  }

  if (!_recognizer) {
    reject(@"NOT_INITIALIZED", @"Call initialize() first", nil);
    return;
  }

  @try {
    AVAuthorizationStatus authStatus = [AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if (authStatus == AVAuthorizationStatusDenied || authStatus == AVAuthorizationStatusRestricted) {
      reject(@"PERMISSION_ERROR", @"Microphone permission denied", nil);
      return;
    }

    AVAudioSession *session = [AVAudioSession sharedInstance];
    NSError *error = nil;
    [session setCategory:AVAudioSessionCategoryPlayAndRecord
                    mode:AVAudioSessionModeDefault
                 options:AVAudioSessionCategoryOptionDefaultToSpeaker
                   error:&error];
    if (error) {
      reject(@"AUDIO_ERROR", error.localizedDescription, error);
      return;
    }
    [session setActive:YES error:&error];
    if (error) {
      reject(@"AUDIO_ERROR", error.localizedDescription, error);
      return;
    }

    _stream = SherpaOnnxCreateOnlineStream(_recognizer);
    _lastText = "";
    [_partialBuffer removeAllObjects];

    _audioEngine = [[AVAudioEngine alloc] init];
    AVAudioInputNode *inputNode = [_audioEngine inputNode];

    // 使用硬件原生格式安装 tap，避免格式不匹配
    AVAudioFormat *hwFormat = [inputNode outputFormatForBus:0];
    AVAudioFormat *targetFormat = [[AVAudioFormat alloc] initWithCommonFormat:AVAudioPCMFormatFloat32
                                                                   sampleRate:16000
                                                                     channels:1
                                                                  interleaved:NO];
    _audioConverter = [[AVAudioConverter alloc] initFromFormat:hwFormat toFormat:targetFormat];

    __weak RNVoiceEngine *weakSelf = self;
    [inputNode installTapOnBus:0 bufferSize:4096 format:hwFormat block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
      [weakSelf processAudioBuffer:buffer targetFormat:targetFormat];
    }];

    [_audioEngine prepare];
    [_audioEngine startAndReturnError:&error];
    if (error) {
      reject(@"AUDIO_ERROR", error.localizedDescription, error);
      return;
    }

    _isRunning = YES;
    NSLog(@"[RNVoiceEngine] Audio engine started");
    resolve(nil);
  } @catch (NSException *exception) {
    reject(@"START_ERROR", exception.reason, nil);
  }
}

RCT_EXPORT_METHOD(stop:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  [self stopInternal];
  resolve(nil);
}

RCT_EXPORT_METHOD(release:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  [self releaseInternal];
  resolve(nil);
}

#pragma mark - Audio Processing

- (void)processAudioBuffer:(AVAudioPCMBuffer *)buffer targetFormat:(AVAudioFormat *)targetFormat {
  if (!_isRunning || !_stream || !_recognizer) return;

  // 重采样到 16kHz
  AVAudioPCMBuffer *convertedBuffer = buffer;
  if (_audioConverter && buffer.format.sampleRate != 16000) {
    AVAudioFrameCount outCapacity = (AVAudioFrameCount)(buffer.frameLength * 16000.0 / buffer.format.sampleRate) + 1;
    convertedBuffer = [[AVAudioPCMBuffer alloc] initWithPCMFormat:targetFormat frameCapacity:outCapacity];
    NSError *convError = nil;
    __block BOOL haveData = YES;
    AVAudioConverterInputBlock inputBlock = ^AVAudioBuffer *(AVAudioPacketCount inNumberOfPackets, AVAudioConverterInputStatus *outStatus) {
      if (haveData) {
        haveData = NO;
        *outStatus = AVAudioConverterInputStatus_HaveData;
        return buffer;
      }
      *outStatus = AVAudioConverterInputStatus_NoDataNow;
      return nil;
    };
    [_audioConverter convertToBuffer:convertedBuffer error:&convError withInputFromBlock:inputBlock];
    if (convError) {
      NSLog(@"[RNVoiceEngine] Audio conversion error: %@", convError);
      return;
    }
  }

  float *data = convertedBuffer.floatChannelData[0];
  int frameLength = (int)convertedBuffer.frameLength;
  if (frameLength <= 0) return;

  // === VAD (optional) ===
  BOOL isSpeech = YES;
  if (_vad) {
    SherpaOnnxVoiceActivityDetectorAcceptWaveform(_vad, data, frameLength);
    isSpeech = SherpaOnnxVoiceActivityDetectorDetected(_vad) == 1;
  }

  // Calculate volume RMS and pitch band (80Hz~260Hz) filtered RMS
  float rms = 0;
  float filteredRms = 0;
  for (int i = 0; i < frameLength; i++) {
    rms += data[i] * data[i];
    float f = _pitchFilter.process(data[i]);
    filteredRms += f * f;
  }
  rms = sqrtf(rms / frameLength);
  filteredRms = sqrtf(filteredRms / frameLength);
  
  float pitchRatio = rms > 1e-6f ? (filteredRms / rms) : 0.0f;
  if (isSpeech && pitchRatio < 0.15f) {
    // Suppress VAD start if the signal lacks fundamental speech pitch energy below 260Hz (typical for smartphone speaker feedback)
    isSpeech = NO;
  }

  static BOOL wasSpeech = NO;

  [self sendEventWithName:@"voiceEngine:volume" body:@{ @"value": @(MIN(1.0f, rms * 5.0f)) }];

  if (isSpeech && !wasSpeech) {
    wasSpeech = YES;
    [self sendEventWithName:@"voiceEngine:vadStart" body:nil];
    [_vadEndTimer invalidate];
    _vadEndTimer = nil;
  }

  if (!isSpeech && wasSpeech) {
    wasSpeech = NO;
    [self sendEventWithName:@"voiceEngine:vadEnd" body:nil];

    // Delay final result to capture trailing audio
    _vadEndTimer = [NSTimer scheduledTimerWithTimeInterval:0.3
                                                    target:self
                                                  selector:@selector(flushFinalResult)
                                                  userInfo:nil
                                                   repeats:NO];
  }

  // === ASR ===
  if (!_isRecognizing) return;

  SherpaOnnxOnlineStreamAcceptWaveform(_stream, 16000, data, frameLength);

  while (SherpaOnnxIsOnlineStreamReady(_recognizer, _stream) == 1) {
    SherpaOnnxDecodeOnlineStream(_recognizer, _stream);
  }

  const SherpaOnnxOnlineRecognizerResult *result = SherpaOnnxGetOnlineStreamResult(_recognizer, _stream);
  if (result && result->text && strlen(result->text) > 0) {
    std::string newText(result->text);
    if (newText != _lastText) {
      _lastText = newText;
      NSString *text = [NSString stringWithUTF8String:result->text];
      [self sendEventWithName:@"voiceEngine:partial" body:@{ @"text": text }];
    }
  }

  SherpaOnnxDestroyOnlineRecognizerResult(result);
}

- (void)flushFinalResult {
  if (!_isRunning) return;

  NSString *text = [NSString stringWithUTF8String:_lastText.c_str()];
  if (text.length > 0) {
    [self sendEventWithName:@"voiceEngine:final" body:@{ @"text": text }];
  }

  // Reset stream for next utterance
  if (_stream) {
    SherpaOnnxDestroyOnlineStream(_stream);
    _stream = SherpaOnnxCreateOnlineStream(_recognizer);
  }
  _lastText = "";
  [_partialBuffer removeAllObjects];
  if (_vad) SherpaOnnxVoiceActivityDetectorReset(_vad);
  _pitchFilter.reset();
}

#pragma mark - TTS Audio Player

RCT_EXPORT_METHOD(playAudioStream:(NSDictionary *)config
                  resolve:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  @try {
    [_audioBuffer setLength:0];
    resolve(nil);
  } @catch (NSException *exception) {
    reject(@"AUDIO_ERROR", exception.reason, nil);
  }
}

RCT_EXPORT_METHOD(writeAudioChunk:(NSString *)base64Data
                  resolve:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  @try {
    NSData *chunk = [[NSData alloc] initWithBase64EncodedString:base64Data options:NSDataBase64DecodingIgnoreUnknownCharacters];
    if (chunk) {
      [_audioBuffer appendData:chunk];
    }

    // 如果还没在播放，尝试开始播放
    if (!_audioPlayer.isPlaying) {
      NSError *error = nil;
      _audioPlayer = [[AVAudioPlayer alloc] initWithData:_audioBuffer error:&error];
      if (error) {
        reject(@"AUDIO_ERROR", error.localizedDescription, error);
        return;
      }
      _audioPlayer.delegate = self;
      [_audioPlayer play];
    }

    resolve(nil);
  } @catch (NSException *exception) {
    reject(@"AUDIO_ERROR", exception.reason, nil);
  }
}

RCT_EXPORT_METHOD(stopAudio:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  [_audioPlayer stop];
  _audioPlayer = nil;
  [_audioBuffer setLength:0];
  resolve(nil);
}

#pragma mark - AVAudioPlayerDelegate

- (void)audioPlayerDidFinishPlaying:(AVAudioPlayer *)player successfully:(BOOL)flag {
  [self sendEventWithName:@"audio:ended" body:nil];
  _audioPlayer = nil;
  [_audioBuffer setLength:0];
}

- (void)audioPlayerDecodeErrorDidOccur:(AVAudioPlayer *)player error:(NSError *)error {
  [self sendEventWithName:@"audio:error" body:@{@"message": error.localizedDescription ?: @"decode error"}];
  _audioPlayer = nil;
  [_audioBuffer setLength:0];
}

#pragma mark - Internal Helpers

- (void)stopInternal {
  _isRunning = NO;
  _isRecognizing = NO;

  if (_audioEngine) {
    [_audioEngine stop];
    [[_audioEngine inputNode] removeTapOnBus:0];
    _audioEngine = nil;
    _audioConverter = nil;
  }

  [_vadEndTimer invalidate];
  _vadEndTimer = nil;

  if (_stream && _recognizer) {
    SherpaOnnxDestroyOnlineStream(_stream);
    _stream = NULL;
  }

  _lastText = "";
  [_partialBuffer removeAllObjects];
}

- (void)releaseInternal {
  [self stopInternal];

  if (_vad) {
    SherpaOnnxDestroyVoiceActivityDetector(_vad);
    _vad = NULL;
  }

  if (_stream) {
    SherpaOnnxDestroyOnlineStream(_stream);
    _stream = NULL;
  }

  if (_recognizer) {
    SherpaOnnxDestroyOnlineRecognizer(_recognizer);
    _recognizer = NULL;
  }

  [_audioPlayer stop];
  _audioPlayer = nil;
  [_audioBuffer setLength:0];
  if (_tts) {
    SherpaOnnxDestroyOfflineTts(_tts);
    _tts = NULL;
  }
  _stringHolders.clear();
}

- (const SherpaOnnxOfflineTts *)getOrInitTTS {
  if (_tts) {
    return _tts;
  }
  
  @try {
    NSBundle *bundle = [NSBundle mainBundle];
    NSString *modelDir = @"sherpa-kokoro";
    NSString *modelPath = [bundle pathForResource:@"model" ofType:@"onnx" inDirectory:modelDir];
    NSString *voicesPath = [bundle pathForResource:@"voices" ofType:@"bin" inDirectory:modelDir];
    NSString *tokensPath = [bundle pathForResource:@"tokens" ofType:@"txt" inDirectory:modelDir];
    NSString *dataDirPath = [bundle pathForResource:@"espeak-ng-data" ofType:nil inDirectory:modelDir];
    NSString *lexiconPath = [bundle pathForResource:@"lexicon-zh" ofType:@"txt" inDirectory:modelDir];
    
    if (!modelPath || !voicesPath || !tokensPath || !dataDirPath) {
      NSLog(@"[RNVoiceEngine] Kokoro TTS assets missing in bundle under '%@'", modelDir);
      return NULL;
    }
    
    _stringHolders.push_back(std::string(modelPath.UTF8String));
    const char *model = _stringHolders.back().c_str();
    
    _stringHolders.push_back(std::string(voicesPath.UTF8String));
    const char *voices = _stringHolders.back().c_str();
    
    _stringHolders.push_back(std::string(tokensPath.UTF8String));
    const char *tokens = _stringHolders.back().c_str();
    
    _stringHolders.push_back(std::string(dataDirPath.UTF8String));
    const char *data_dir = _stringHolders.back().c_str();
    
    const char *lexicon = "";
    if (lexiconPath) {
      _stringHolders.push_back(std::string(lexiconPath.UTF8String));
      lexicon = _stringHolders.back().c_str();
    }
    
    SherpaOnnxOfflineTtsConfig config = {};
    config.model.kokoro.model = model;
    config.model.kokoro.voices = voices;
    config.model.kokoro.tokens = tokens;
    config.model.kokoro.data_dir = data_dir;
    config.model.kokoro.length_scale = 1.0f;
    config.model.kokoro.dict_dir = "";
    config.model.kokoro.lexicon = lexicon;
    config.model.kokoro.lang = "";
    config.model.num_threads = 2;
    config.model.provider = "cpu";
    
    _tts = SherpaOnnxCreateOfflineTts(&config);
    if (!_tts) {
      NSLog(@"[RNVoiceEngine] Failed to create Offline TTS");
    } else {
      NSLog(@"[RNVoiceEngine] Offline Kokoro TTS initialized successfully");
    }
  } @catch (NSException *e) {
    NSLog(@"[RNVoiceEngine] Exception in getOrInitTTS: %@", e.reason);
  }
  return _tts;
}

RCT_EXPORT_METHOD(setVadThreshold:(double)threshold
                  resolve:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  @synchronized(self) {
    _vadThreshold = (float)threshold;
    NSLog(@"[RNVoiceEngine] Updated VAD threshold to %f", threshold);
  }
  resolve(nil);
}

RCT_EXPORT_METHOD(synthesizeTTS:(NSDictionary *)params
                  resolve:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  NSString *text = params[@"text"] ?: @"";
  int speakerId = params[@"speakerId"] != nil ? [params[@"speakerId"] intValue] : 0;
  float speed = params[@"speed"] != nil ? [params[@"speed"] floatValue] : 1.0f;
  
  if (text.length == 0) {
    resolve(@"");
    return;
  }
  
  dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
    @synchronized(self) {
      const SherpaOnnxOfflineTts *tts = [self getOrInitTTS];
      if (!tts) {
        reject(@"TTS_ERROR", @"TTS engine not initialized", nil);
        return;
      }
      
      SherpaOnnxGenerationConfig genConfig = {};
      genConfig.sid = speakerId;
      genConfig.speed = speed;
      genConfig.silence_scale = 0.2f;
      
      const SherpaOnnxGeneratedAudio *audio = SherpaOnnxOfflineTtsGenerateWithConfig(
        tts,
        text.UTF8String,
        &genConfig,
        NULL,
        NULL
      );
      
      if (!audio || !audio->samples || audio->n <= 0) {
        reject(@"TTS_ERROR", @"Failed to generate audio samples", nil);
        return;
      }
      
      NSString *tempDir = NSTemporaryDirectory();
      NSString *fileName = [NSString stringWithFormat:@"tts_%f_%d.wav", [[NSDate date] timeIntervalSince1970], arc4random_uniform(1000)];
      NSString *filePath = [tempDir stringByAppendingPathComponent:fileName];
      
      int32_t success = SherpaOnnxWriteWave(audio->samples, audio->n, audio->sample_rate, filePath.UTF8String);
      SherpaOnnxDestroyOfflineTtsGeneratedAudio(audio);
      
      if (success != 1) {
        reject(@"TTS_ERROR", @"Failed to write WAV file", nil);
        return;
      }
      
      resolve(filePath);
    }
  });
}

@end
