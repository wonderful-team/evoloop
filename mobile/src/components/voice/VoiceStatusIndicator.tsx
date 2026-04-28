// 语音状态指示器 - 显示当前语音会话状态

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { Text } from 'react-native-paper';
import { VoiceSessionState } from '@/types/voice';
import { useTheme } from '@/theme';

interface VoiceStatusIndicatorProps {
  state: VoiceSessionState;
  volume?: number;
}

export function VoiceStatusIndicator({ state, volume = 0 }: VoiceStatusIndicatorProps) {
  const { colors } = useTheme();

  // 动画值
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const waveAnims = useRef([
    new Animated.Value(0),
    new Animated.Value(0),
    new Animated.Value(0),
  ]).current;

  // 根据状态启动不同动画
  useEffect(() => {
    let animation: Animated.CompositeAnimation | null = null;

    if (state === 'listening') {
      // 监听状态 - 脉冲动画
      animation = Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, {
            toValue: 1.2,
            duration: 800,
            useNativeDriver: true,
          }),
          Animated.timing(pulseAnim, {
            toValue: 1,
            duration: 800,
            useNativeDriver: true,
          }),
        ])
      );
    } else if (state === 'speaking') {
      // 说话状态 - 波浪动画
      animation = Animated.loop(
        Animated.stagger(200,
          waveAnims.map((anim) =>
            Animated.sequence([
              Animated.timing(anim, {
                toValue: 1,
                duration: 400,
                useNativeDriver: true,
              }),
              Animated.timing(anim, {
                toValue: 0,
                duration: 400,
                useNativeDriver: true,
              }),
            ])
          )
        )
      );
    }

    animation?.start();

    return () => {
      animation?.stop();
      pulseAnim.setValue(1);
      waveAnims.forEach((anim) => anim.setValue(0));
    };
  }, [state, pulseAnim, waveAnims]);

  // 获取状态显示文本
  const getStatusText = () => {
    switch (state) {
      case 'idle':
        return '点击开始对话';
      case 'connecting':
        return '连接中...';
      case 'listening':
        return '聆听中...';
      case 'recognizing':
        return '识别中...';
      case 'thinking':
        return '思考中...';
      case 'speaking':
        return '回答中...';
      default:
        return '';
    }
  };

  // 获取状态颜色
  const getStatusColor = () => {
    switch (state) {
      case 'listening':
        return colors.status.info;
      case 'thinking':
      case 'recognizing':
        return colors.status.warning;
      case 'speaking':
        return colors.primary;
      default:
        return colors.text.secondary;
    }
  };

  // 根据音量计算波形高度
  const getWaveHeight = (index: number) => {
    const baseHeight = 20 + index * 10;
    const volumeFactor = Math.max(0.3, volume);
    return baseHeight * volumeFactor;
  };

  const statusColor = getStatusColor();

  return (
    <View style={styles.container}>
      {/* 状态动画区域 */}
      <View style={styles.animationContainer}>
        {state === 'listening' && (
          <Animated.View
            style={[
              styles.pulseRing,
              {
                backgroundColor: statusColor,
                transform: [{ scale: pulseAnim }],
                opacity: pulseAnim.interpolate({
                  inputRange: [1, 1.2],
                  outputRange: [0.5, 0.2],
                }),
              },
            ]}
          />
        )}

        {state === 'speaking' && (
          <View style={styles.waveContainer}>
            {waveAnims.map((anim, index) => (
              <Animated.View
                key={index}
                style={[
                  styles.waveBar,
                  {
                    backgroundColor: statusColor,
                    height: getWaveHeight(index),
                    transform: [
                      {
                        scaleY: anim.interpolate({
                          inputRange: [0, 1],
                          outputRange: [0.5, 1],
                        }),
                      },
                    ],
                    opacity: anim.interpolate({
                      inputRange: [0, 1],
                      outputRange: [0.5, 1],
                    }),
                  },
                ]}
              />
            ))}
          </View>
        )}

        {state === 'thinking' && (
          <View style={styles.dotsContainer}>
            {[0, 1, 2].map((index) => (
              <Animated.View
                key={index}
                style={[
                  styles.dot,
                  {
                    backgroundColor: statusColor,
                    transform: [
                      {
                        translateY: pulseAnim.interpolate({
                          inputRange: [1, 1.2],
                          outputRange: [0, -8],
                        }),
                      },
                    ],
                  },
                ]}
              />
            ))}
          </View>
        )}
      </View>

      {/* 状态文本 */}
      <Text
        variant="bodyMedium"
        style={[styles.statusText, { color: statusColor }]}
      >
        {getStatusText()}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  animationContainer: {
    width: 80,
    height: 80,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  pulseRing: {
    width: 60,
    height: 60,
    borderRadius: 30,
    position: 'absolute',
  },
  waveContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    height: 60,
  },
  waveBar: {
    width: 6,
    borderRadius: 3,
  },
  dotsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    textAlign: 'center',
  },
});
