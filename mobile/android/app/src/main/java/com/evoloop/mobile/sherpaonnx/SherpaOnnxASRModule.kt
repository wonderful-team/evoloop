package com.evoloop.mobile.sherpaonnx

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.app.ActivityCompat
import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import com.k2fsa.sherpa.onnx.*
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

/**
 * React Native 桥接模块：Sherpa-ONNX 流式 ASR
 *
 * 纯本地运行。使用 AudioRecord 采集音频，在独立线程中进行流式 ASR 推理。
 * 识别结果通过 "onAsrResult" 事件发送到 JS 层，由 JS 层做唤醒词匹配。
 */
class SherpaOnnxASRModule(reactContext: ReactApplicationContext) :
  ReactContextBaseJavaModule(reactContext) {

  companion object {
    private const val TAG = "SherpaOnnxASR"
    private const val SAMPLE_RATE = 16000
    private const val CHUNK_SIZE = SAMPLE_RATE / 10 // 100ms chunks
  }

  override fun getName() = "SherpaOnnxASR"

  private var recognizer: OnlineRecognizer? = null
  private var stream: OnlineStream? = null
  private var audioRecord: AudioRecord? = null
  private val running = AtomicBoolean(false)
  private var executor: java.util.concurrent.ExecutorService? = null
  private var lastText = ""

  /**
   * 初始化 OnlineRecognizer（加载模型）
   */
  @ReactMethod
  fun init(configMap: ReadableMap, promise: Promise) {
    try {
      releaseInternal()

      val assetManager = reactApplicationContext.assets
      val modelDir = configMap.getString("modelDir") ?: ""
      val numThreads = if (configMap.hasKey("numThreads")) configMap.getInt("numThreads") else 2

      // 验证模型文件在 assets 中存在
      try {
        assetManager.open("$modelDir/encoder-epoch-99-avg-1.int8.onnx").close()
        assetManager.open("$modelDir/decoder-epoch-99-avg-1.int8.onnx").close()
        assetManager.open("$modelDir/joiner-epoch-99-avg-1.int8.onnx").close()
        assetManager.open("$modelDir/tokens.txt").close()
      } catch (e: java.io.IOException) {
        promise.reject("INIT_ERROR", "Model files not found in assets: ${e.message}", e)
        return
      }

      val config = OnlineRecognizerConfig(
        featConfig = FeatureConfig(sampleRate = SAMPLE_RATE, featureDim = 80),
        modelConfig = OnlineModelConfig(
          transducer = OnlineTransducerModelConfig(
            encoder = "$modelDir/encoder-epoch-99-avg-1.int8.onnx",
            decoder = "$modelDir/decoder-epoch-99-avg-1.int8.onnx",
            joiner = "$modelDir/joiner-epoch-99-avg-1.int8.onnx",
          ),
          tokens = "$modelDir/tokens.txt",
          numThreads = numThreads,
          provider = "cpu",
          modelType = "zipformer",
        ),
        decodingMethod = "greedy_search",
        maxActivePaths = 4,
      )

      recognizer = OnlineRecognizer(assetManager = assetManager, config = config)
      lastText = ""
      Log.d(TAG, "OnlineRecognizer initialized with modelDir=$modelDir")
      promise.resolve(null)
    } catch (e: Exception) {
      Log.e(TAG, "Init failed", e)
      promise.reject("INIT_ERROR", e.message, e)
    }
  }

  /**
   * 启动音频采集和 ASR 推理
   */
  @ReactMethod
  fun start(promise: Promise) {
    try {
      if (running.get()) {
        promise.resolve(null)
        return
      }

      val context = reactApplicationContext
      if (ActivityCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
        != PackageManager.PERMISSION_GRANTED
      ) {
        promise.reject("PERMISSION_ERROR", "RECORD_AUDIO permission not granted")
        return
      }

      val rec = recognizer ?: run {
        promise.reject("NOT_INITIALIZED", "Call init() first")
        return
      }

      stream = rec.createStream()
      Log.d(TAG, "OnlineStream created")

      val channelConfig = AudioFormat.CHANNEL_IN_MONO
      val audioFormat = AudioFormat.ENCODING_PCM_16BIT
      val bufferSize = maxOf(
        AudioRecord.getMinBufferSize(SAMPLE_RATE, channelConfig, audioFormat),
        SAMPLE_RATE * 2
      )

      val recorder = AudioRecord(
        MediaRecorder.AudioSource.MIC,
        SAMPLE_RATE,
        channelConfig,
        audioFormat,
        bufferSize
      )

      if (recorder.state != AudioRecord.STATE_INITIALIZED) {
        promise.reject("AUDIO_ERROR", "Failed to initialize AudioRecord")
        recorder.release()
        return
      }

      audioRecord = recorder
      recorder.startRecording()
      running.set(true)
      lastText = ""

      executor = Executors.newSingleThreadExecutor()
      executor?.submit {
        processAudio()
      }

      Log.d(TAG, "Audio recording started")
      promise.resolve(null)
    } catch (e: Exception) {
      Log.e(TAG, "Start failed", e)
      promise.reject("START_ERROR", e.message, e)
    }
  }

  /**
   * 停止音频采集
   */
  @ReactMethod
  fun stop(promise: Promise) {
    try {
      stopInternal()
      promise.resolve(null)
    } catch (e: Exception) {
      Log.e(TAG, "Stop failed", e)
      promise.reject("STOP_ERROR", e.message, e)
    }
  }

  /**
   * 释放所有资源
   */
  @ReactMethod
  fun release(promise: Promise) {
    try {
      releaseInternal()
      promise.resolve(null)
    } catch (e: Exception) {
      Log.e(TAG, "Release failed", e)
      promise.reject("RELEASE_ERROR", e.message, e)
    }
  }

  private fun stopInternal() {
    running.set(false)
    audioRecord?.stop()
    audioRecord?.release()
    audioRecord = null
    stream?.release()
    stream = null
    executor?.shutdown()
    executor = null
    Log.d(TAG, "Stopped")
  }

  private fun releaseInternal() {
    stopInternal()
    recognizer?.release()
    recognizer = null
    lastText = ""
  }

  /**
   * 音频处理线程：读取 AudioRecord 数据，送入 ASR 引擎
   */
  private fun processAudio() {
    val recorder = audioRecord ?: return
    val s = stream ?: return
    val rec = recognizer ?: return

    val shortBuffer = ShortArray(CHUNK_SIZE)

    try {
      while (running.get()) {
        val read = recorder.read(shortBuffer, 0, shortBuffer.size)
        if (read <= 0) continue

        // 16-bit PCM → float (-1.0 ~ 1.0)
        val floatSamples = FloatArray(read) { shortBuffer[it] / 32768.0f }
        s.acceptWaveform(floatSamples, SAMPLE_RATE)

        // 解码循环
        while (rec.isReady(s)) {
          rec.decode(s)
        }

        val result = rec.getResult(s)
        if (result.text.isNotEmpty() && result.text != lastText) {
          lastText = result.text
          Log.d(TAG, "ASR result: ${result.text}")
          val params = Arguments.createMap()
          params.putString("text", result.text)
          emitEvent("onAsrResult", params)
        }
      }
    } catch (e: Exception) {
      Log.e(TAG, "Audio processing error", e)
      if (running.get()) {
        val params = Arguments.createMap()
        params.putString("message", e.message ?: "Unknown error")
        emitEvent("onError", params)
      }
    }
  }

  private fun emitEvent(eventName: String, params: WritableMap?) {
    reactApplicationContext
      .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
      .emit(eventName, params)
  }
}
