// 语音模式可视化面板 - 从 VoiceInput 中提取

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Text } from 'react-native-paper';
import { VoiceVisualizer } from '@/components/chat/VoiceVisualizer';

interface VoiceInputVoicePanelProps {
  isListening: boolean;
  nlsVolume?: number;
  transcriptionText?: string;
}

export function VoiceInputVoicePanel({
  isListening,
  nlsVolume,
  transcriptionText,
}: VoiceInputVoicePanelProps) {
  if (!isListening) return null;

  return (
    <>
      {/* 录音时显示均衡器可视化 */}
      {nlsVolume !== undefined && (
        <View style={styles.visualizerContainer}>
          <VoiceVisualizer
            volume={nlsVolume}
            isRecording={isListening}
            barCount={15}
            height={60}
          />
        </View>
      )}

      {/* 实时转录文字显示 */}
      {transcriptionText ? (
        <View style={styles.transcriptionContainer}>
          <Text
            variant="bodyLarge"
            style={styles.transcriptionText}
            numberOfLines={2}
          >
            {transcriptionText}
          </Text>
        </View>
      ) : (
        <View style={styles.transcriptionContainer}>
          <Text variant="bodyMedium" style={styles.listeningHint}>
            正在聆听...
          </Text>
        </View>
      )}
    </>
  );
}

const styles = StyleSheet.create({
  visualizerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: 8,
    width: '100%',
  },
  transcriptionContainer: {
    alignItems: 'center',
    paddingHorizontal: 24,
    marginBottom: 8,
    width: '100%',
  },
  transcriptionText: {
    textAlign: 'center',
    fontSize: 18,
    lineHeight: 26,
  },
  listeningHint: {
    textAlign: 'center',
    opacity: 0.6,
  },
});
