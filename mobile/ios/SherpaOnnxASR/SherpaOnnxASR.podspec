Pod::Spec.new do |s|
  s.name         = "SherpaOnnxASR"
  s.version      = "1.0.0"
  s.summary      = "Sherpa ONNX Streaming ASR for React Native"
  s.description  = "React Native native module bridging sherpa-onnx streaming ASR for wake word detection"
  s.homepage     = "https://github.com/k2-fsa/sherpa-onnx"
  s.license      = "Apache-2.0"
  s.author       = { "EvoLoop" => "dev@evoloop.ai" }
  s.platforms    = { :ios => "16.0" }
  s.source       = { :git => "https://github.com/k2-fsa/sherpa-onnx.git", :tag => "v1.0.0" }

  s.requires_arc = true
  s.source_files = "*.{h,mm}"

  # Prebuilt frameworks copied from expo-sherpa-onnx
  s.vendored_frameworks = [
    '../Frameworks/sherpa-onnx.xcframework',
    '../Frameworks/onnxruntime.xcframework',
    '../Frameworks/libarchive.xcframework',
  ]

  s.pod_target_xcconfig = {
    'HEADER_SEARCH_PATHS' => '"${PODS_TARGET_SRCROOT}/../Frameworks/sherpa-onnx.xcframework/ios-arm64_x86_64-simulator/Headers" "${PODS_TARGET_SRCROOT}/../Frameworks/sherpa-onnx.xcframework/ios-arm64/Headers"',
    'FRAMEWORK_SEARCH_PATHS' => '"${PODS_TARGET_SRCROOT}/../Frameworks"',
  }

  s.user_target_xcconfig = {
    'LIBRARY_SEARCH_PATHS' => '"${PODS_ROOT}/../Frameworks/sherpa-onnx.xcframework/ios-arm64_x86_64-simulator" "${PODS_ROOT}/../Frameworks/onnxruntime.xcframework/ios-arm64_x86_64-simulator" "${PODS_ROOT}/../Frameworks/libarchive.xcframework/ios-arm64_x86_64-simulator"',
    'OTHER_LDFLAGS' => '$(inherited) -lsherpa-onnx "${PODS_ROOT}/../Frameworks/onnxruntime.xcframework/ios-arm64_x86_64-simulator/onnxruntime.a" -larchive',
  }

  s.dependency 'React-Core'
end
