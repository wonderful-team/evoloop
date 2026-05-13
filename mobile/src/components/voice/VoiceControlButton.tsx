// 语音控制按钮 - 大圆形按钮，支持点击/长按

import React, { useRef } from 'react';
import {
  View,
  StyleSheet,
  Animated,
  Pressable,
  GestureResponderEvent,
} from 'react-native';
import { IconButton } from 'react-native-paper';
import { useTheme } from '@/theme';
import { VoiceSessionState } from '@/types/voice';

interface VoiceControlButtonProps {
  state: VoiceSessionState;
  volume?: number;
  onPress: () => void;
  onLongPress?: () => void;
  onPressOut?: () => void;
  disabled?: boolean;
}

export function VoiceControlButton({
  state,
  volume = 0,
  onPress,
  onLongPress,
  onPressOut,
  disabled = false,
}: VoiceControlButtonProps) {
  const { colors } = useTheme();
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const isListening = state === 'listening';
  const isProcessing = state === 'thinking' || state === 'recognizing';
  const isSpeaking = state === 'speaking';
  const isActive = isListening || isSpeaking;

  // 处理按下
  const handlePressIn = (event: GestureResponderEvent) => {
    Animated.spring(scaleAnim, {
      toValue: 0.9,
      useNativeDriver: true,
      friction: 5,
    }).start();
  };

  // 处理释放
  const handlePressOut = (event: GestureResponderEvent) => {
    Animated.spring(scaleAnim, {
      toValue: 1,
      useNativeDriver: true,
      friction: 5,
    }).start();

    onPressOut?.();
  };

  // 根据状态获取按钮颜色
  const getButtonColor = () => {
    if (isListening) return colors.status.error;
    if (isSpeaking) return colors.primary;
    if (isProcessing) return colors.status.warning;
    return colors.primary;
  };

  // 根据状态获取图标
  const getIcon = () => {
    if (isListening) return 'microphone';
    if (isSpeaking) return 'volume-high';
    if (isProcessing) return 'loading';
    return 'microphone';
  };

  const buttonColor = getButtonColor();

  // 根据音量计算波纹大小
  const waveScale = 1 + Math.min(volume * 0.5, 0.3);

  return (
    <Pressable
      onPressIn={handlePressIn}
      onPressOut={handlePressOut}
      onPress={onPress}
      onLongPress={onLongPress}
      disabled={disabled || isProcessing}
      style={styles.container}
    >
      <Animated.View
        style={[
          styles.buttonContainer,
          { transform: [{ scale: scaleAnim }] },
        ]}
      >
        {/* 背景波纹效果（仅监听状态时） */}
        {isListening && (
          <>
            <Animated.View
              style={[
                styles.wave,
                styles.wave1,
                {
                  backgroundColor: buttonColor,
                  opacity: 0.3,
                  transform: [{ scale: waveScale }],
                },
              ]}
            />
            <Animated.View
              style={[
                styles.wave,
                styles.wave2,
                {
                  backgroundColor: buttonColor,
                  opacity: 0.2,
                  transform: [{ scale: waveScale * 1.2 }],
                },
              ]}
            />
          </>
        )}

        {/* 主按钮 */}
        <View
          style={[
            styles.button,
            {
              backgroundColor: buttonColor,
              shadowColor: buttonColor,
            },
          ]}
        >
          <IconButton
            icon={getIcon()}
            size={40}
            iconColor={isListening ? colors.onError : isProcessing ? colors.onWarning : colors.onPrimary}
            style={styles.icon}
          />
        </View>

      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonContainer: {
    width: 120,
    height: 120,
    alignItems: 'center',
    justifyContent: 'center',
  },
  wave: {
    position: 'absolute',
    width: 120,
    height: 120,
    borderRadius: 60,
  },
  wave1: {},
  wave2: {
    width: 140,
    height: 140,
    borderRadius: 70,
  },
  button: {
    width: 100,
    height: 100,
    borderRadius: 50,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 8,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  icon: {
    margin: 0,
  },
});
