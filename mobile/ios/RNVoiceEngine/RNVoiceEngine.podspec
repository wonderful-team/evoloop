Pod::Spec.new do |s|
  s.name         = "RNVoiceEngine"
  s.version      = "1.0.0"
  s.summary      = "EvoLoop Voice Engine (ASR + VAD + Wake) for React Native"
  s.description  = "React Native native module bridging sherpa-onnx streaming ASR with VAD"
  s.homepage     = "https://github.com/evoloop/mobile"
  s.license      = "Apache-2.0"
  s.author       = { "EvoLoop" => "dev@evoloop.ai" }
  s.platforms    = { :ios => "16.0" }
  s.source       = { :git => "https://github.com/evoloop/mobile.git", :tag => "v1.0.0" }

  s.requires_arc = true
  s.source_files = "*.{h,mm}"

  s.pod_target_xcconfig = {
    'HEADER_SEARCH_PATHS' => '"${PODS_TARGET_SRCROOT}/../Frameworks/sherpa-onnx.xcframework/ios-arm64_x86_64-simulator/Headers" "${PODS_TARGET_SRCROOT}/../Frameworks/sherpa-onnx.xcframework/ios-arm64/Headers"',
    'FRAMEWORK_SEARCH_PATHS' => '"${PODS_TARGET_SRCROOT}/../Frameworks"',
  }

  s.vendored_frameworks = [
    '../Frameworks/sherpa-onnx.xcframework',
    '../Frameworks/onnxruntime.xcframework',
    '../Frameworks/libarchive.xcframework',
  ]

  # ASR + Kokoro TTS 模型资源
  s.resources = [
    '../EvoLoopMobile/Resources/sherpa-asr/**/*',
    '../EvoLoopMobile/Resources/sherpa-kokoro/**/*',
  ]

  s.dependency 'React-Core'
end
