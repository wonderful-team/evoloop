// 配额耗尽顶部横幅 - 对应 Desktop 的 QuotaExhaustedBanner
// 当 LLM 配额耗尽时显示在聊天区域顶部

import React from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { Text } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

interface QuotaExhaustedBannerProps {
  title?: string;
  message?: string;
}

export function QuotaExhaustedBanner({ title, message }: QuotaExhaustedBannerProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  // 脉冲动画
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

  const displayTitle = title || t('chat.quota.banner.title');
  const displayMessage = message || t('chat.quota.banner.message');

  return (
    <Animated.View
      style={[
        styles.container,
        {
          backgroundColor: colors.errorContainer + '40',
          borderBottomColor: colors.error + '30',
          transform: [{ scale: pulseAnim }],
        },
      ]}
    >
      <View style={styles.content}>
        <MaterialIcons name="warning" size={18} color={colors.error} />
        <Text style={[styles.title, { color: colors.error }]}>
          {displayTitle}
        </Text>
        <Text style={[styles.message, { color: colors.error + 'CC' }]}>
          - {displayMessage}
        </Text>
      </View>
    </Animated.View>
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
  title: {
    fontSize: 14,
    fontWeight: '600',
  },
  message: {
    fontSize: 13,
  },
});
