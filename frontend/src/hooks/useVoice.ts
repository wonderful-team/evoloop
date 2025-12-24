import { useState, useCallback, useEffect } from "react"
import { invoke, addPluginListener } from "@tauri-apps/api/core"
import { toast } from "sonner"

export interface UseVoiceOptions {
    language?: string
}

interface RecognitionResult {
    transcript: string;
    isFinal: boolean;
}

export function useVoice(options: UseVoiceOptions = {}) {
    const [isListening, setIsListening] = useState(false)
    const [isSpeaking, setIsSpeaking] = useState(false)
    const [transcript, setTranscript] = useState("")

    useEffect(() => {
        // Store unlisten functions
        let listenerRx: any = undefined;
        let listenerErr: any = undefined;

        const setupListeners = async () => {
            try {
                // Mobile listener setup
                listenerRx = await addPluginListener('stt', 'result', (event: any) => {
                    const payload = event.payload as RecognitionResult;
                    if (payload && payload.transcript) {
                        setTranscript(payload.transcript)
                    }
                });

                listenerErr = await addPluginListener('stt', 'error', (event: any) => {
                    console.error("STT Error Event Raw:", JSON.stringify(event));

                    let errorMsg = "Unknown Error";
                    // Handle Tauri v2 Event<T> structure OR direct payload
                    const payload = event.payload || event;

                    if (payload) {
                        if (typeof payload === 'string') {
                            errorMsg = payload;
                        } else if (typeof payload === 'object') {
                            // Try to extract standard error fields
                            errorMsg = payload.message || payload.error || JSON.stringify(payload);
                            // Add code/details if present
                            if (payload.code) errorMsg = `[${payload.code}] ${errorMsg}`;
                            if (payload.details) errorMsg += ` (${payload.details})`;
                        }
                    }

                    toast.error("STT Error: " + errorMsg);

                    // Ensure state is reset
                    setIsListening(false);
                    // Try to force stop to sync state
                    invoke('plugin:stt|stop_listening').catch(console.error);
                });

                // Check availability
                try {
                    const avail: any = await invoke('plugin:stt|is_available');
                    if (!avail?.available) {
                        toast.error("STT Service not available: " + (avail?.reason || "Unknown reason"));
                    }
                } catch (e) {
                    console.error("Failed to check availability:", e);
                }

                // Check languages (only log warning if missing)
                try {
                    const langs: any = await invoke('plugin:stt|get_supported_languages');
                    if (Array.isArray(langs)) {
                        const targetLang = options.language || 'zh-CN';
                        const hasLang = langs.some((l: any) => l.code === targetLang || l === targetLang);
                        if (!hasLang) {
                            toast.warning(`STT: ${targetLang} not found in supported languages.`);
                        }
                    }
                } catch (e) {
                    console.error("Failed to get languages:", e);
                }

            } catch (err) {
                console.error("Failed to setup STT listeners", err)
            }
        };

        setupListeners();

        // Check permissions
        invoke('plugin:stt|check_permission').then((perm: any) => {
            if (perm?.microphone !== 'granted' && perm?.speechRecognition !== 'granted') {
                invoke('plugin:stt|request_permission').catch(console.error);
            }
        }).catch(console.error);

        // Ensure clean start
        invoke('plugin:stt|stop_listening').catch(() => { })

        return () => {
            if (typeof listenerRx === 'function') listenerRx();
            if (typeof listenerErr === 'function') listenerErr();
            invoke('plugin:stt|stop_listening').catch(() => { })
        }
    }, [options.language])

    const startListening = useCallback(async () => {
        try {
            if (isListening) return

            // Force stop first to prevent "Already listening" state desync
            await invoke('plugin:stt|stop_listening').catch(console.warn)

            // Short delay to allow OS to release mic
            await new Promise(resolve => setTimeout(resolve, 150));

            setTranscript("")
            setIsListening(true)

            await invoke('plugin:stt|start_listening', {
                config: {
                    language: options.language || "zh-CN",
                    interimResults: false, // Try false to reduce load
                    continuous: false, // Try false for stability
                }
            })

        } catch (error) {
            console.error("Failed to start listening:", error)
            toast.error("STT Start Error: " + JSON.stringify(error))
            setIsListening(false)
        }
    }, [options.language, isListening])

    const stopListening = useCallback(async () => {
        try {
            await invoke('plugin:stt|stop_listening')
            setIsListening(false)
        } catch (error) {
            console.error("Failed to stop listening:", error)
            toast.error("STT Stop Error: " + JSON.stringify(error))
        }
    }, [])

    const speak = useCallback(async (text: string) => {
        try {
            setIsSpeaking(true)
            await invoke('plugin:tts|speak', {
                payload: {
                    text,
                    language: options.language || "zh-CN",
                    queueMode: "flush",
                }
            })
            setIsSpeaking(false)
        } catch (error) {
            console.error("Failed to speak:", error)
            setIsSpeaking(false)
        }
    }, [options.language])

    const stopSpeaking = useCallback(async () => {
        try {
            await invoke('plugin:tts|stop')
            setIsSpeaking(false)
        } catch (error) {
            console.error("Failed to stop speaking:", error)
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
