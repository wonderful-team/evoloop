// 语音可视化组件 - 动态均衡器效果
import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { useTheme } from '@/theme';

interface VoiceVisualizerProps {
  /** 音量值 0-1 */
  volume: number;
  /** 是否正在录音 */
  isRecording: boolean;
  /** 柱子数量 */
  barCount?: number;
  /** 柱子颜色 */
  color?: string;
  /** 组件高度 */
  height?: number;
}

/**
 * 动态均衡器可视化组件
 * 模拟音频频谱效果，多个柱子独立跳动
 */
export function VoiceVisualizer({
  volume,
  isRecording,
  barCount = 5,
  color,
  height = 60,
}: VoiceVisualizerProps) {
  const { colors } = useTheme();
  const barColor = color || colors.primary;

  // 为每个柱子创建动画值
  const barAnimations = useRef<Animated.Value[]>(
    Array(barCount).fill(0).map(() => new Animated.Value(0.3))
  ).current;

  // 根据音量和随机因子计算柱子高度
  useEffect(() => {
    if (!isRecording) {
      // 停止录音时，所有柱子回到基础高度
      barAnimations.forEach(anim => {
        Animated.spring(anim, {
          toValue: 0.1,
          useNativeDriver: false, // height 动画不支持原生驱动
          friction: 8,
        }).start();
      });
      return;
    }

    // 录音中：根据音量动态调整柱子高度
    // 添加随机性模拟真实频谱效果
    barAnimations.forEach((anim, index) => {
      // 每个柱子有不同的敏感度和相位
      const sensitivity = 0.8 + Math.random() * 0.4; // 0.8 - 1.2
      const phase = Math.sin(Date.now() / 200 + index * 0.5); // 正弦波动
      const randomNoise = (Math.random() - 0.5) * 0.3; // 随机噪声

      // 计算目标高度 (0.1 - 1.0)
      let targetHeight = 0.1 + volume * sensitivity + phase * 0.1 + randomNoise;
      targetHeight = Math.max(0.1, Math.min(1, targetHeight));

      Animated.spring(anim, {
        toValue: targetHeight,
        useNativeDriver: false, // height 动画不支持原生驱动
        friction: 4,
        tension: 40,
      }).start();
    });
  }, [volume, isRecording, barAnimations]);

  // 持续动画效果（即使音量不变，也有轻微的律动）
  useEffect(() => {
    if (!isRecording) return;

    const interval = setInterval(() => {
      barAnimations.forEach((anim, index) => {
        // 添加微小的随机波动
        const fluctuation = (Math.random() - 0.5) * 0.15;
        const currentBase = 0.1 + volume * 0.8;
        let newValue = currentBase + fluctuation;

        // 不同柱子有不同的响应特性
        if (index === Math.floor(barCount / 2)) {
          // 中间柱子响应最强
          newValue += volume * 0.2;
        } else if (index === 0 || index === barCount - 1) {
          // 两边柱子响应较弱
          newValue -= 0.1;
        }

        newValue = Math.max(0.1, Math.min(1, newValue));

        Animated.spring(anim, {
          toValue: newValue,
          useNativeDriver: false, // height 动画不支持原生驱动
          friction: 5,
          tension: 50,
        }).start();
      });
    }, 100); // 每 100ms 更新一次

    return () => clearInterval(interval);
  }, [isRecording, volume, barAnimations, barCount]);

  return (
    <View style={[styles.container, { height }]}>
      {barAnimations.map((anim, index) => (
        <View key={index} style={styles.barContainer}>
          <Animated.View
            style={[
              styles.bar,
              {
                backgroundColor: barColor,
                opacity: 0.6 + (index / barCount) * 0.4, // 渐变透明度
                height: anim.interpolate({
                  inputRange: [0, 1],
                  outputRange: ['10%', '100%'],
                }),
              },
            ]}
          />
        </View>
      ))}
    </View>
  );
}

/**
 * 简洁版均衡器 - 用于小空间展示
 */
export function CompactVoiceVisualizer({
  volume,
  isRecording,
  color,
}: Omit<VoiceVisualizerProps, 'barCount' | 'height'>) {
  return (
    <VoiceVisualizer
      volume={volume}
      isRecording={isRecording}
      barCount={3}
      height={30}
      color={color}
    />
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'flex-end', // 底部对齐，让柱子从底部生长
    justifyContent: 'center',
    gap: 4,
    width: '100%',
    paddingHorizontal: 20,
  },
  barContainer: {
    flex: 1,
    height: '100%',
    justifyContent: 'flex-end', // 底部对齐
    maxWidth: 8,
  },
  bar: {
    width: '100%',
    borderRadius: 4,
  },
});

export default VoiceVisualizer;
