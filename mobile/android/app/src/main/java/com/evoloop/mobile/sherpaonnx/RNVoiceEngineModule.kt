package com.evoloop.mobile.sherpaonnx

import android.Manifest
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.audiofx.NoiseSuppressor
import android.media.MediaRecorder
import android.util.Log
import androidx.core.app.ActivityCompat
import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import com.k2fsa.sherpa.onnx.*
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.sqrt

/**
 * React Native 桥接模块：RNVoiceEngine
 * 封装 Sherpa-ONNX 流式 ASR + VAD + 音量事件
 * VAD 在 Android 上先以音量阈值简单实现，后续可替换为 Silero VAD JNI
 */
import java.io.File
import java.io.FileOutputStream
import android.media.MediaPlayer
import android.util.Base64

class BiquadFilter {
  private var b0 = 0f
  private var b1 = 0f
  private var b2 = 0f
  private var a1 = 0f
  private var a2 = 0f
  private var x1 = 0f
  private var x2 = 0f
  private var y1 = 0f
  private var y2 = 0f

  init {
    val w0 = 2.0 * Math.PI * 170.0 / 16000.0
    val alpha = Math.sin(w0) / (2.0 * 0.94)

    val b0_d = alpha
    val b1_d = 0.0
    val b2_d = -alpha
    val a0_d = 1.0 + alpha
    val a1_d = -2.0 * Math.cos(w0)
    val a2_d = 1.0 - alpha

    b0 = (b0_d / a0_d).toFloat()
    b1 = (b1_d / a0_d).toFloat()
    b2 = (b2_d / a0_d).toFloat()
    a1 = (a1_d / a0_d).toFloat()
    a2 = (a2_d / a0_d).toFloat()
  }

  fun process(x: Float): Float {
    val y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
    x2 = x1
    x1 = x
    y2 = y1
    y1 = y
    return y
  }

  fun reset() {
    x1 = 0f
    x2 = 0f
    y1 = 0f
    y2 = 0f
  }
}

class RNVoiceEngineModule(reactContext: ReactApplicationContext) :
  ReactContextBaseJavaModule(reactContext) {

  companion object {
    private const val TAG = "RNVoiceEngine"
    private const val SAMPLE_RATE = 16000
    private const val CHUNK_SIZE = SAMPLE_RATE / 10
    private const val VAD_ENERGY_THRESHOLD = 500.0
    private const val SILENCE_FRAMES_THRESHOLD = 8
  }

  override fun getName() = "RNVoiceEngine"

  private var recognizer: OnlineRecognizer? = null
  private var stream: OnlineStream? = null
  private var audioRecord: AudioRecord? = null
  private val running = AtomicBoolean(false)
  private val isRecognizing = AtomicBoolean(false)
  private var executor: java.util.concurrent.ExecutorService? = null
  private var lastText = ""
  private var mode = "idle"

  private var consecutiveSpeechFrames = 0
  private var consecutiveSilenceFrames = 0
  private var isSpeaking = false

  // TTS audio buffer
  private val audioBuffer = StringBuilder()
  private var mediaPlayer: MediaPlayer? = null

  private var offlineTts: OfflineTts? = null
  private val pitchFilter = BiquadFilter()
  private var vadThreshold = VAD_ENERGY_THRESHOLD
  private var energyThreshold = 0.02f

  private fun copyAssetsFolder(srcFolder: String, destFolder: File) {
    val assetManager = reactApplicationContext.assets
    val files = assetManager.list(srcFolder) ?: return
    if (!destFolder.exists()) {
      destFolder.mkdirs()
    }
    for (filename in files) {
      val assetPath = if (srcFolder.isEmpty()) filename else "$srcFolder/$filename"
      val destFile = File(destFolder, filename)
      val subFiles = assetManager.list(assetPath)
      if (!subFiles.isNullOrEmpty()) {
        copyAssetsFolder(assetPath, destFile)
      } else {
        if (destFile.exists() && destFile.length() > 0) {
          continue
        }
        assetManager.open(assetPath).use { input ->
          FileOutputStream(destFile).use { output ->
            input.copyTo(output)
          }
        }
      }
    }
  }

  @Synchronized
  private fun getOrInitTTS(): OfflineTts? {
    val tts = offlineTts
    if (tts != null) return tts

    try {
      val localTtsDir = File(reactApplicationContext.filesDir, "sherpa-kokoro")
      copyAssetsFolder("sherpa-kokoro", localTtsDir)

      val kokoroConfig = OfflineTtsKokoroModelConfig.builder()
        .setModel(File(localTtsDir, "model.onnx").absolutePath)
        .setVoices(File(localTtsDir, "voices.bin").absolutePath)
        .setTokens(File(localTtsDir, "tokens.txt").absolutePath)
        .setDataDir(File(localTtsDir, "espeak-ng-data").absolutePath)
        .setLexicon(File(localTtsDir, "lexicon-zh.txt").absolutePath)
        .build()

      val modelConfig = OfflineTtsModelConfig.builder()
        .setKokoro(kokoroConfig)
        .setNumThreads(2)
        .setProvider("cpu")
        .build()

      val ttsConfig = OfflineTtsConfig.builder()
        .setModel(modelConfig)
        .setSilenceScale(0.2f)
        .build()

      offlineTts = OfflineTts(ttsConfig)
      Log.d(TAG, "Offline Kokoro TTS initialized successfully")
    } catch (e: Exception) {
      Log.e(TAG, "Failed to initialize Offline Kokoro TTS", e)
    }
    return offlineTts
  }

  @ReactMethod
  fun initialize(configMap: ReadableMap, promise: Promise) {
    try {
      releaseInternal()

      val assetManager = reactApplicationContext.assets
      val modelDir = configMap.getString("modelDir") ?: ""
      val numThreads = if (configMap.hasKey("numThreads")) configMap.getInt("numThreads") else 2
      energyThreshold = if (configMap.hasKey("energyThreshold")) configMap.getDouble("energyThreshold").toFloat() else 0.02f

      // 验证模型文件
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
      Log.d(TAG, "Initialized with modelDir=$modelDir")
      promise.resolve(null)
    } catch (e: Exception) {
      Log.e(TAG, "Init failed", e)
      promise.reject("INIT_ERROR", e.message, e)
    }
  }

  @ReactMethod
  fun setMode(modeStr: String, promise: Promise) {
    mode = modeStr
    isRecognizing.set(mode == "asr")
    promise.resolve(null)
  }

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

      NoiseSuppressor.create(recorder.audioSessionId)

      audioRecord = recorder
      recorder.startRecording()
      running.set(true)
      lastText = ""
      consecutiveSpeechFrames = 0
      consecutiveSilenceFrames = 0
      isSpeaking = false

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

  @ReactMethod
  fun playAudioStream(config: ReadableMap, promise: Promise) {
    audioBuffer.setLength(0)
    promise.resolve(null)
  }

  @ReactMethod
  fun writeAudioChunk(base64Data: String, promise: Promise) {
    try {
      audioBuffer.append(base64Data)
      val decoded = Base64.decode(base64Data, Base64.DEFAULT)
      if (decoded.size < 44) {
        // 还没收到完整 wav header，不播放
        promise.resolve(null)
        return
      }

      val tempFile = File(reactApplicationContext.cacheDir, "tts_${System.currentTimeMillis()}.wav")
      FileOutputStream(tempFile).use { it.write(decoded) }

      stopMediaPlayer()
      mediaPlayer = MediaPlayer().apply {
        setDataSource(tempFile.absolutePath)
        setOnCompletionListener {
          emitEvent("audio:ended", null)
          tempFile.delete()
        }
        setOnErrorListener { _, _, _ ->
          emitEvent("audio:error", Arguments.createMap().apply { putString("message", "media player error") })
          tempFile.delete()
          true
        }
        prepare()
        start()
      }
      promise.resolve(null)
    } catch (e: Exception) {
      Log.e(TAG, "writeAudioChunk failed", e)
      promise.reject("AUDIO_ERROR", e.message, e)
    }
  }

  @ReactMethod
  fun stopAudio(promise: Promise) {
    stopMediaPlayer()
    audioBuffer.setLength(0)
    promise.resolve(null)
  }

  private fun stopMediaPlayer() {
    try {
      mediaPlayer?.stop()
    } catch (_: Exception) {}
    mediaPlayer?.release()
    mediaPlayer = null
  }

  private fun releaseInternal() {
    stopInternal()
    stopMediaPlayer()
    audioBuffer.setLength(0)
    recognizer?.release()
    recognizer = null
    offlineTts?.release()
    offlineTts = null
    lastText = ""
  }

  private fun stopInternal() {
    running.set(false)
    isRecognizing.set(false)
    audioRecord?.stop()
    audioRecord?.release()
    audioRecord = null
    stream?.release()
    stream = null
    executor?.let { e ->
      e.shutdown()
      try {
        e.awaitTermination(500, java.util.concurrent.TimeUnit.MILLISECONDS)
      } catch (_: InterruptedException) {
        e.shutdownNow()
      }
    }
    executor = null
    isSpeaking = false
    Log.d(TAG, "Stopped")
  }

  private fun processAudio() {
    val shortBuffer = ShortArray(CHUNK_SIZE)

    try {
      while (running.get()) {
        val recorder = audioRecord ?: break
        val s = stream ?: break
        val rec = recognizer ?: break

        val read = recorder.read(shortBuffer, 0, shortBuffer.size)
        if (read <= 0) {
          Thread.sleep(10)
          continue
        }

        // Volume / simple VAD and pitch ratio check
        val energy = calculateEnergy(shortBuffer, read)
        val volume = minOf(1.0, energy / 10000.0)
        emitEvent("voiceEngine:volume", Arguments.createMap().apply {
          putDouble("value", volume)
        })

        // Calculate pitch ratio (80Hz~260Hz) for loudspeaker leak detection
        var pitchSum = 0.0
        var totalSum = 0.0
        for (i in 0 until read) {
          val sample = shortBuffer[i].toFloat() / 32768.0f
          totalSum += sample * sample
          val f = pitchFilter.process(sample)
          pitchSum += f * f
        }
        val rms = sqrt(totalSum / read)
        val filteredRms = sqrt(pitchSum / read)
        val pitchRatio = if (rms > 1e-6f) (filteredRms / rms).toFloat() else 0.0f

        // Energy gate: skip VAD/ASR for low-energy noise floor
        if (rms < energyThreshold) continue

        var speechDetected = energy > vadThreshold
        if (speechDetected && pitchRatio < 0.15f) {
          // Suppress VAD due to high probability of speaker feedback leak
          speechDetected = false
        }

        if (speechDetected) {
          consecutiveSpeechFrames++
          consecutiveSilenceFrames = 0
          if (consecutiveSpeechFrames >= 2 && !isSpeaking) {
            isSpeaking = true
            emitEvent("voiceEngine:vadStart", null)
          }
        } else {
          consecutiveSilenceFrames++
          consecutiveSpeechFrames = 0
          if (consecutiveSilenceFrames >= SILENCE_FRAMES_THRESHOLD && isSpeaking) {
            isSpeaking = false
            emitEvent("voiceEngine:vadEnd", null)
            flushFinalResult(s, rec)
          }
        }

        // ASR
        if (!isRecognizing.get()) continue

        val floatSamples = FloatArray(read) { shortBuffer[it] / 32768.0f }
        s.acceptWaveform(floatSamples, SAMPLE_RATE)

        while (rec.isReady(s)) {
          rec.decode(s)
        }

        val result = rec.getResult(s)
        if (result.text.isNotEmpty() && result.text != lastText) {
          lastText = result.text
          Log.d(TAG, "ASR result: ${result.text}")
          emitEvent("voiceEngine:partial", Arguments.createMap().apply {
            putString("text", result.text)
          })
        }
      }
    } catch (e: Exception) {
      Log.e(TAG, "Audio processing error", e)
      if (running.get()) {
        emitEvent("voiceEngine:error", Arguments.createMap().apply {
          putString("message", e.message ?: "Unknown error")
        })
      }
    }
  }

  private fun flushFinalResult(s: OnlineStream, rec: OnlineRecognizer) {
    if (lastText.isNotEmpty()) {
      emitEvent("voiceEngine:final", Arguments.createMap().apply {
        putString("text", lastText)
      })
    }

    // Reset stream for next utterance
    s.release()
    stream = rec.createStream()
    lastText = ""
    pitchFilter.reset()
  }

  private fun calculateEnergy(data: ShortArray, length: Int): Double {
    var sum = 0.0
    for (i in 0 until length) {
      val sample = data[i].toDouble()
      sum += sample * sample
    }
    return sqrt(sum / length)
  }

  private fun emitEvent(eventName: String, params: WritableMap?) {
    reactApplicationContext
      .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
      .emit(eventName, params)
  }

  @ReactMethod
  fun setVadThreshold(threshold: Double, promise: Promise) {
    vadThreshold = threshold * 1000.0
    Log.d(TAG, "Dynamically updated VAD threshold to $vadThreshold")
    promise.resolve(null)
  }

  @ReactMethod
  fun synthesizeTTS(params: ReadableMap, promise: Promise) {
    val text = params.getString("text") ?: ""
    val speakerId = if (params.hasKey("speakerId")) params.getInt("speakerId") else 0
    val speed = if (params.hasKey("speed")) params.getDouble("speed").toFloat() else 1.0f

    if (text.isEmpty()) {
      promise.resolve("")
      return
    }

    Thread {
      synchronized(this) {
        val tts = getOrInitTTS()
        if (tts == null) {
          promise.reject("TTS_ERROR", "TTS engine not initialized")
          return@Thread
        }

        try {
          val audio = tts.generate(text, speakerId, speed)
          if (audio == null || audio.samples == null || audio.samples.isEmpty()) {
            promise.reject("TTS_ERROR", "Failed to generate audio samples")
            return@Thread
          }

          val tempFile = File(reactApplicationContext.cacheDir, "tts_${System.currentTimeMillis()}_${(0..1000).random()}.wav")
          val saved = audio.save(tempFile.absolutePath)
          if (!saved) {
            promise.reject("TTS_ERROR", "Failed to save generated audio wav file")
            return@Thread
          }

          promise.resolve(tempFile.absolutePath)
        } catch (e: Exception) {
          Log.e(TAG, "synthesizeTTS failed", e)
          promise.reject("TTS_ERROR", e.message, e)
        }
      }
    }.start()
  }
}
