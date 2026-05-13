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

  s.source_files = "*.{h,mm}"

  # Prebuilt frameworks copied from expo-sherpa-onnx
  s.vendored_frameworks = [
    '../Frameworks/sherpa-onnx.xcframework',
    '../Frameworks/onnxruntime.xcframework',
    '../Frameworks/libarchive.xcframework',
  ]

  s.dependency 'React-Core'
end
