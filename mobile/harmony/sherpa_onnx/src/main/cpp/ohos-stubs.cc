#include "include/sherpa-onnx/c-api/c-api.h"

#ifdef __OHOS__
extern "C" {

SHERPA_ONNX_API const SherpaOnnxOfflineSpeechDenoiser *
SherpaOnnxCreateOfflineSpeechDenoiserOHOS(
    const SherpaOnnxOfflineSpeechDenoiserConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOnlineSpeechDenoiser *
SherpaOnnxCreateOnlineSpeechDenoiserOHOS(
    const SherpaOnnxOnlineSpeechDenoiserConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOnlineRecognizer *
SherpaOnnxCreateOnlineRecognizerOHOS(
    const SherpaOnnxOnlineRecognizerConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOfflineRecognizer *
SherpaOnnxCreateOfflineRecognizerOHOS(
    const SherpaOnnxOfflineRecognizerConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxVoiceActivityDetector *
SherpaOnnxCreateVoiceActivityDetectorOHOS(
    const SherpaOnnxVadModelConfig *config,
    float buffer_size_in_seconds,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOfflineTts *
SherpaOnnxCreateOfflineTtsOHOS(
    const SherpaOnnxOfflineTtsConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOfflinePunctuation *
SherpaOnnxCreateOfflinePunctuationOHOS(
    const SherpaOnnxOfflinePunctuationConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOnlinePunctuation *
SherpaOnnxCreateOnlinePunctuationOHOS(
    const SherpaOnnxOnlinePunctuationConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxSpeakerEmbeddingExtractor *
SherpaOnnxCreateSpeakerEmbeddingExtractorOHOS(
    const SherpaOnnxSpeakerEmbeddingExtractorConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxKeywordSpotter *
SherpaOnnxCreateKeywordSpotterOHOS(
    const SherpaOnnxKeywordSpotterConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOfflineSpeakerDiarization *
SherpaOnnxCreateOfflineSpeakerDiarizationOHOS(
    const SherpaOnnxOfflineSpeakerDiarizationConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

SHERPA_ONNX_API const SherpaOnnxOfflineSourceSeparation *
SherpaOnnxCreateOfflineSourceSeparationOHOS(
    const SherpaOnnxOfflineSourceSeparationConfig *config,
    NativeResourceManager *mgr) {
  return nullptr;
}

}
#endif
