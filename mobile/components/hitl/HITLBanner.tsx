// HITL 顶部横幅 - 对应 Desktop 的 HITLBanner
// 当 Agent 等待人类输入时显示

import React from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { Text } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import { MaterialIcons } from '@expo/vector-icons';
import { useHITLStore } from '@/stores/hitlStore';

interface HITLBannerProps {
  /** 自定义提示文本 */
  message?: string;
}

export function HITLBanner({ message }: HITLBannerProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const currentRequest = useHITLStore((state) => state.currentRequest);
  const isWaiting = useHITLStore((state) => state.isWaiting);

  // 只有等待状态才显示
  if (!isWaiting || !currentRequest) {
    return null;
  }

  // 使用脉冲动画
  const pulseAnim = React.useRef(new Animated.Value(1)).current;

  React.useEffect(() => {
    const pulse = Animated.sequence([
      Animated.timing(pulseAnim, {
        toValue: 1.05,
        duration: 1000,
        useNativeDriver: true,
      }),
      Animated.timing(pulseAnim, {
        toValue: 1,
        duration: 1000,
        useNativeDriver: true,
      }),
    ]);

    const loop = Animated.loop(pulse);
    loop.start();

    return () => {
      loop.stop();
    };
  }, [pulseAnim]);

  // 默认提示消息
  const defaultMessage = t('hitl.waiting');
  const displayMessage = message || defaultMessage;

  return (
    <Animated.View
      style={[
        styles.container,
        {
          backgroundColor: colors.warningContainer,
          borderBottomColor: colors.warning,
          transform: [{ scale: pulseAnim }],
        },
      ]}
    >
      <View style={styles.content}>
        <MaterialIcons name="person-outline" size={18} color={colors.onWarningContainer} />
        <Text style={[styles.text, { color: colors.onWarningContainer }]}>
          {displayMessage}
        </Text>
        <View style={[styles.dot, { backgroundColor: colors.warning }]} />
      </View>
    </Animated.View>
  );
}

// 紧凑型版本（用于嵌入消息列表）
export function HITLBannerCompact() {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const isWaiting = useHITLStore((state) => state.isWaiting);
  const currentRequest = useHITLStore((state) => state.currentRequest);

  if (!isWaiting || !currentRequest) {
    return null;
  }

  return (
    <View style={[styles.compactContainer, { backgroundColor: colors.warningContainer }]}>
      <MaterialIcons name="person-outline" size={16} color={colors.onWarningContainer} />
      <Text style={[styles.compactText, { color: colors.onWarningContainer }]}>
        {t('hitl.waiting')}
      </Text>
    </View>
  );
}

// HITL 状态指示器（小圆点）
export function HITLIndicator() {
  const { colors } = useTheme();
  const isWaiting = useHITLStore((state) => state.isWaiting);

  if (!isWaiting) {
    return null;
  }

  return (
    <View style={[styles.indicator, { backgroundColor: colors.warning }]}>
      <View style={[styles.indicatorInner, { backgroundColor: colors.onWarning }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderBottomWidth: 1,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  text: {
    fontSize: 14,
    fontWeight: '500',
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    alignSelf: 'flex-start',
  },
  compactText: {
    fontSize: 12,
    fontWeight: '500',
  },
  indicator: {
    width: 12,
    height: 12,
    borderRadius: 6,
    justifyContent: 'center',
    alignItems: 'center',
  },
  indicatorInner: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
});
