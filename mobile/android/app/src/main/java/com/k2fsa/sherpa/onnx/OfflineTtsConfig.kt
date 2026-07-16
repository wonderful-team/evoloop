package com.k2fsa.sherpa.onnx

data class OfflineTtsConfig(
    var model: OfflineTtsModelConfig = OfflineTtsModelConfig(),
    var silenceScale: Float = 1.0f,
) {
    class Builder {
        private var model = OfflineTtsModelConfig()
        private var silenceScale = 1.0f

        fun setModel(v: OfflineTtsModelConfig) = apply { model = v }
        fun setSilenceScale(v: Float) = apply { silenceScale = v }
        fun build() = OfflineTtsConfig(model, silenceScale)
    }

    companion object {
        fun builder() = Builder()
    }
}
