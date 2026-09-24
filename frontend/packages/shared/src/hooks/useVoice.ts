import {useCallback, useEffect, useRef, useState} from "react"
import {useTranslation} from "react-i18next"
import {toast} from "sonner"

export interface UseVoiceOptions {
  language?: string
}

export function useVoice(options: UseVoiceOptions = {}) {
  const { t } = useTranslation()
  const [isListening, setIsListening] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [transcript, setTranscript] = useState("")

  // Refs to hold instances
  const recognitionRef = useRef<any | null>(null)
  const synthesisRef = useRef<SpeechSynthesis>(window.speechSynthesis)

  useEffect(() => {
    // Initialize Speech Recognition
    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition

    if (SpeechRecognition) {
      const recognition = new SpeechRecognition()
      recognition.continuous = true // Keep listening until stopped
      recognition.interimResults = true // Show partial results
      recognition.lang = options.language || "zh-CN"

      recognition.onresult = (event: any) => {
        let finalTranscript = ""
        let interimTranscript = ""

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript
          } else {
            interimTranscript += event.results[i][0].transcript
          }
        }

        // We mainly care about the latest result for chat input
        // Or accumulate? The existing implementation seemed to replace.
        // Let's set the current valid transcript.
        const currentText = finalTranscript || interimTranscript
        if (currentText) {
          setTranscript(currentText)
        }
      }

      recognition.onerror = (event: any) => {
        console.error("Speech Recognition Error:", event.error)
        if (event.error === "no-speech") {
          return // Ignore
        }
        toast.error(`${t("voice.micError")}${event.error}`)
        setIsListening(false)
      }

      recognition.onend = () => {
        setIsListening(false)
      }

      recognitionRef.current = recognition
    } else {
      console.warn(t("voice.webSpeechNotSupported"))
    }

    return () => {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop()
        } catch (_e) {}
      }
      if (synthesisRef.current) {
        synthesisRef.current.cancel()
      }
    }
  }, [options.language, t])

  const startListening = useCallback(async () => {
    if (!recognitionRef.current) {
      toast.error(t("voice.notSupported"))
      return
    }

    if (isListening) return

    try {
      setTranscript("")
      recognitionRef.current.start()
      setIsListening(true)
    } catch (error) {
      console.error("Failed to start recognition:", error)
      // Sometimes it throws if already started
      setIsListening(false)
    }
  }, [isListening, t])

  const stopListening = useCallback(async () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop()
      setIsListening(false)
    }
  }, [])

  const speak = useCallback(
    (text: string) => {
      if (!synthesisRef.current) return

      // Cancel current speak
      synthesisRef.current.cancel()

      const utterance = new SpeechSynthesisUtterance(text)
      utterance.lang = options.language || "zh-CN"

      utterance.onstart = () => setIsSpeaking(true)
      utterance.onend = () => setIsSpeaking(false)
      utterance.onerror = (e) => {
        console.error("TTS Error:", e)
        setIsSpeaking(false)
      }

      synthesisRef.current.speak(utterance)
    },
    [options.language],
  )

  const stopSpeaking = useCallback(() => {
    if (synthesisRef.current) {
      synthesisRef.current.cancel()
      setIsSpeaking(false)
    }
  }, [])

  return {
    isListening,
    isSpeaking,
    transcript,
    startListening,
    stopListening,
    speak,
    stopSpeaking,
  }
}
