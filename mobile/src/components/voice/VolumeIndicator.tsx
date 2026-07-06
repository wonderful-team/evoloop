// 音量指示器 - 实时显示录音音量

import React from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';

interface VolumeIndicatorProps {
  volume: number; // 0-1
  bars?: number;
}

export function VolumeIndicator({ volume, bars = 20 }: VolumeIndicatorProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  // 生成条形图
  const renderBars = () => {
    const barArray = [];

    for (let i = 0; i < bars; i++) {
      // 计算每个条形的激活阈值
      const threshold = (i + 1) / bars;
      const isActive = volume >= threshold;

      // 根据位置计算颜色渐变
      const progress = i / bars;
      let barColor = colors.status.error;
      if (progress < 0.6) {
        barColor = colors.status.success;
      } else if (progress < 0.8) {
        barColor = colors.status.warning;
      }

      barArray.push(
        <View
          key={i}
          style={[
            styles.bar,
            {
              backgroundColor: isActive ? barColor : colors.surfaceVariant,
              height: 8 + i * 2,
            },
          ]}
        />
      );
    }

    return barArray;
  };

  return (
    <View style={styles.container}>
      <View style={styles.barsContainer}>{renderBars()}</View>
      {/* 音量百分比 */}
      <Animated.Text style={[styles.volumeText, { color: colors.text.secondary }]}>
        {Math.round(volume * 100)}{t('common.units.percent')}
      </Animated.Text>
    </View>
  );
}

// 简化版音量指示器（水平条形）
export function VolumeBar({ volume }: { volume: number }) {
  const { colors } = useTheme();

  // 根据音量选择颜色
  let barColor = colors.status.success;
  if (volume > 0.6) {
    barColor = colors.status.warning;
  }
  if (volume > 0.8) {
    barColor = colors.status.error;
  }

  return (
    <View style={styles.barContainer}>
      <View
        style={[
          styles.barBackground,
          { backgroundColor: colors.surfaceVariant },
        ]}
      >
        <View
          style={[
            styles.barFill,
            {
              width: `${volume * 100}%`,
              backgroundColor: barColor,
            },
          ]}
        />
      </View>
    </View>
  );
}

// 圆形音量指示器
export function VolumeCircle({ volume, size = 120 }: { volume: number; size?: number }) {
  const { colors } = useTheme();

  // 计算圆环进度
  const circumference = 2 * Math.PI * (size / 2 - 10);
  const strokeDashoffset = circumference * (1 - volume);

  // 根据音量选择颜色
  let strokeColor = colors.status.success;
  if (volume > 0.6) {
    strokeColor = colors.status.warning;
  }
  if (volume > 0.8) {
    strokeColor = colors.status.error;
  }

  return (
    <View style={[styles.circleContainer, { width: size, height: size }]}>
      {/* 背景圆环 */}
      <View
        style={[
          styles.circle,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            borderColor: colors.surfaceVariant,
          },
        ]}
      />
      {/* 进度圆环 - 使用 SVG 或简化版 */}
      <View
        style={[
          styles.circleProgress,
          {
            width: size,
            height: size,
            borderRadius: size / 2,
            borderColor: strokeColor,
            opacity: volume,
            transform: [{ scale: 0.5 + volume * 0.5 }],
          },
        ]}
      />
      {/* 中心音量百分比 */}
      <View style={styles.circleTextContainer}>
        <Animated.Text style={[styles.circleText, { color: colors.text.primary }]}>
          {Math.round(volume * 100)}
        </Animated.Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  barsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 3,
    height: 60,
  },
  bar: {
    width: 6,
    borderRadius: 3,
  },
  volumeText: {
    marginTop: 8,
    fontSize: 12,
  },
  barContainer: {
    padding: 16,
  },
  barBackground: {
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
  },
  barFill: {
    height: '100%',
    borderRadius: 4,
  },
  circleContainer: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  circle: {
    position: 'absolute',
    borderWidth: 4,
  },
  circleProgress: {
    position: 'absolute',
    borderWidth: 4,
  },
  circleTextContainer: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  circleText: {
    fontSize: 24,
    fontWeight: 'bold',
  },
});
