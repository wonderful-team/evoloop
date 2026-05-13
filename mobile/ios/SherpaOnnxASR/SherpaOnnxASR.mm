//
//  SherpaOnnxASR.mm
//  SherpaOnnxASR React Native Native Module
//

#import "SherpaOnnxASR.h"
#import <AVFoundation/AVFoundation.h>
#include <string>
#include <vector>
#include "sherpa-onnx/c-api/c-api.h"

@interface SherpaOnnxASR () {
  const SherpaOnnxOnlineRecognizer *_recognizer;
  const SherpaOnnxOnlineStream *_stream;
  AVAudioEngine *_audioEngine;
  BOOL _isRunning;
  std::string _lastText;
  std::vector<std::string> _stringHolders;
}
@end

@implementation SherpaOnnxASR

RCT_EXPORT_MODULE(SherpaOnnxASR);

+ (BOOL)requiresMainQueueSetup {
  return YES;
}

- (NSArray<NSString *> *)supportedEvents {
  return @[ @"onAsrResult", @"onError" ];
}

- (instancetype)init {
  self = [super init];
  if (self) {
    _recognizer = NULL;
    _stream = NULL;
    _audioEngine = nil;
    _isRunning = NO;
  }
  return self;
}

- (void)dealloc {
  [self releaseInternal];
}

#pragma mark - Public Methods

RCT_EXPORT_METHOD(init:(NSDictionary *)config
                  resolve:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  [self releaseInternal];
  _stringHolders.clear();

  @try {
    NSString *modelDir = config[@"modelDir"] ?: @"";
    int numThreads = config[@"numThreads"] != nil ? [config[@"numThreads"] intValue] : 2;

    NSBundle *bundle = [NSBundle mainBundle];

    auto resolvePath = ^NSString *(NSString *resource, NSString *ext) {
      NSString *path = [bundle pathForResource:resource ofType:ext inDirectory:modelDir];
      if (!path) {
        path = [bundle pathForResource:resource ofType:ext inDirectory:@"sherpa-asr"];
      }
      if (!path) {
        path = [bundle pathForResource:resource ofType:ext];
      }
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

    SherpaOnnxFeatureConfig featConfig = {
      .sample_rate = 16000,
      .feature_dim = 80,
    };

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

    _stream = SherpaOnnxCreateOnlineStream(_recognizer);
    if (!_stream) {
      SherpaOnnxDestroyOnlineRecognizer(_recognizer);
      _recognizer = NULL;
      reject(@"INIT_ERROR", @"Failed to create OnlineStream", nil);
      return;
    }

    _lastText = "";
    NSLog(@"[SherpaOnnxASR] Initialized");
    resolve(nil);
  } @catch (NSException *exception) {
    reject(@"INIT_ERROR", exception.reason, nil);
  }
}

RCT_EXPORT_METHOD(start:(RCTPromiseResolveBlock)resolve
                  reject:(RCTPromiseRejectBlock)reject) {
  if (_isRunning) {
    resolve(nil);
    return;
  }

  if (!_recognizer || !_stream) {
    reject(@"NOT_INITIALIZED", @"Call init() first", nil);
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

    _audioEngine = [[AVAudioEngine alloc] init];
    AVAudioInputNode *inputNode = [_audioEngine inputNode];

    AVAudioFormat *format = [[AVAudioFormat alloc] initWithCommonFormat:AVAudioPCMFormatFloat32
                                                             sampleRate:16000
                                                               channels:1
                                                            interleaved:NO];

    __weak typeof(self) weakSelf = self;
    [inputNode installTapOnBus:0 bufferSize:1600 format:format block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
      [weakSelf processAudioBuffer:buffer];
    }];

    [_audioEngine prepare];
    [_audioEngine startAndReturnError:&error];
    if (error) {
      reject(@"AUDIO_ERROR", error.localizedDescription, error);
      return;
    }

    _isRunning = YES;
    _lastText = "";
    NSLog(@"[SherpaOnnxASR] Audio engine started");
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

- (void)processAudioBuffer:(AVAudioPCMBuffer *)buffer {
  if (!_isRunning || !_stream || !_recognizer) return;

  float *data = buffer.floatChannelData[0];
  int frameLength = (int)buffer.frameLength;
  if (frameLength <= 0) return;

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
      NSLog(@"[SherpaOnnxASR] ASR result: %@", text);
      [self sendEventWithName:@"onAsrResult" body:@{ @"text": text }];
    }
  }

  SherpaOnnxDestroyOnlineRecognizerResult(result);
}

#pragma mark - Internal Helpers

- (void)stopInternal {
  _isRunning = NO;

  if (_audioEngine) {
    [_audioEngine stop];
    [[_audioEngine inputNode] removeTapOnBus:0];
    _audioEngine = nil;
  }

  if (_stream && _recognizer) {
    SherpaOnnxDestroyOnlineStream(_stream);
    _stream = SherpaOnnxCreateOnlineStream(_recognizer);
  }

  _lastText = "";
}

- (void)releaseInternal {
  [self stopInternal];

  if (_stream) {
    SherpaOnnxDestroyOnlineStream(_stream);
    _stream = NULL;
  }

  if (_recognizer) {
    SherpaOnnxDestroyOnlineRecognizer(_recognizer);
    _recognizer = NULL;
  }

  _stringHolders.clear();
}

@end
