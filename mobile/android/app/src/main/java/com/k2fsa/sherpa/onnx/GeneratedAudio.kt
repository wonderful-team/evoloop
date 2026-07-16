package com.k2fsa.sherpa.onnx

class GeneratedAudio(private var ptr: Long) {
    private var _samples: FloatArray? = null
    private var _sampleRate: Int = 0

    val samples: FloatArray
        get() {
            if (_samples == null) {
                _samples = getSamples(ptr)
            }
            return _samples!!
        }

    val sampleRate: Int
        get() {
            if (_sampleRate == 0) {
                _sampleRate = getSampleRate(ptr)
            }
            return _sampleRate
        }

    fun save(filename: String): Boolean = synchronized(this) {
        if (ptr == 0L) return false
        return saveImpl(ptr, filename)
    }

    protected fun finalize() {
        synchronized(this) {
            if (ptr != 0L) {
                delete(ptr)
                ptr = 0
            }
        }
    }

    private external fun getSamples(ptr: Long): FloatArray
    private external fun getSampleRate(ptr: Long): Int
    private external fun saveImpl(ptr: Long, filename: String): Boolean
    private external fun delete(ptr: Long)

    companion object {
        init {
            System.loadLibrary("sherpa-onnx-jni")
        }
    }
}
