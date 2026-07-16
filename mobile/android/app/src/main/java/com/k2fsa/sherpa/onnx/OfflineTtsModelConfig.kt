package com.k2fsa.sherpa.onnx

data class OfflineTtsModelConfig(
    var kokoro: OfflineTtsKokoroModelConfig = OfflineTtsKokoroModelConfig(),
    var numThreads: Int = 1,
    var debug: Boolean = false,
    var provider: String = "cpu",
) {
    class Builder {
        private var kokoro = OfflineTtsKokoroModelConfig()
        private var numThreads = 1
        private var debug = false
        private var provider = "cpu"

        fun setKokoro(v: OfflineTtsKokoroModelConfig) = apply { kokoro = v }
        fun setNumThreads(v: Int) = apply { numThreads = v }
        fun setDebug(v: Boolean) = apply { debug = v }
        fun setProvider(v: String) = apply { provider = v }
        fun build() = OfflineTtsModelConfig(kokoro, numThreads, debug, provider)
    }

    companion object {
        fun builder() = Builder()
    }
}
