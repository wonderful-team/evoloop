declare module 'tauri-plugin-stt-api' {
    export function checkPermission(): Promise<boolean>;
    export function requestPermission(): Promise<void>;
    export function startListening(options: { language: string, partialResults?: boolean, onResult?: (res: any) => void, onStateChange?: (state: any) => void, onError?: (err: any) => void }): Promise<void>;
    export function stopListening(): Promise<void>;
    export function onResult(callback: (result: any) => void): Promise<() => void>;
}

declare module 'tauri-plugin-tts-api' {
    export function speak(options: { text: string, queueMode?: string }): Promise<void>;
    export function stop(): Promise<void>;
}
