import { useEffect } from 'react';
import { DeviceEventEmitter, Platform } from 'react-native';

interface SystemVoiceIntentEvent {
  text: string;
}

export function useSystemIntent(onReceiveIntentText: (text: string) => void) {
  useEffect(() => {
    if (Platform.OS !== 'harmony') {
      return;
    }

    const subscription = DeviceEventEmitter.addListener(
      'onSystemVoiceIntent',
      (event: SystemVoiceIntentEvent) => {
        console.log('[SystemIntent] 收到小艺发送的文本指令:', event.text);
        if (event.text) {
          onReceiveIntentText(event.text);
        }
      }
    );

    return () => {
      subscription.remove();
    };
  }, [onReceiveIntentText]);
}
