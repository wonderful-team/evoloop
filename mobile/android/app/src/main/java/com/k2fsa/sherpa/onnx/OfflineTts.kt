package com.k2fsa.sherpa.onnx

class OfflineTts(config: OfflineTtsConfig) {
    private var ptr: Long

    init {
        ptr = newFromFile(config)
    }

    fun generate(text: String, sid: Int, speed: Float): GeneratedAudio? = synchronized(this) {
        if (ptr == 0L) return null
        val audioPtr = generateImpl(ptr, text, sid, speed)
        if (audioPtr == 0L) return null
        return GeneratedAudio(audioPtr)
    }

    val sampleRate: Int get() = synchronized(this) {
        if (ptr == 0L) return 0
        return getSampleRate(ptr)
    }

    fun release() {
        synchronized(this) {
            if (ptr != 0L) {
                delete(ptr)
                ptr = 0
            }
        }
    }

    protected fun finalize() {
        release()
    }

    private external fun newFromFile(config: OfflineTtsConfig): Long
    private external fun delete(ptr: Long)
    private external fun generateImpl(ptr: Long, text: String, sid: Int, speed: Float): Long
    private external fun getSampleRate(ptr: Long): Int

    companion object {
        init {
            System.loadLibrary("sherpa-onnx-jni")
        }
    }
}
