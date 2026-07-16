package com.k2fsa.sherpa.onnx

data class OfflineTtsKokoroModelConfig(
    var model: String = "",
    var voices: String = "",
    var tokens: String = "",
    var dataDir: String = "",
    var lexicon: String = "",
    var lang: String = "",
    var lengthScale: Float = 1.0f,
) {
    class Builder {
        private var model = ""
        private var voices = ""
        private var tokens = ""
        private var dataDir = ""
        private var lexicon = ""
        private var lang = ""
        private var lengthScale = 1.0f

        fun setModel(v: String) = apply { model = v }
        fun setVoices(v: String) = apply { voices = v }
        fun setTokens(v: String) = apply { tokens = v }
        fun setDataDir(v: String) = apply { dataDir = v }
        fun setLexicon(v: String) = apply { lexicon = v }
        fun setLang(v: String) = apply { lang = v }
        fun setLengthScale(v: Float) = apply { lengthScale = v }
        fun build() = OfflineTtsKokoroModelConfig(model, voices, tokens, dataDir, lexicon, lang, lengthScale)
    }

    companion object {
        fun builder() = Builder()
    }
}
