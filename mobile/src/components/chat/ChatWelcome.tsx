import React, { useState, useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { Text } from 'react-native-paper';
import Animated, { 
  useSharedValue, 
  useAnimatedStyle, 
  withTiming
} from 'react-native-reanimated';
import { WoodenRobot } from '@/components/WoodenRobot';
import { useTheme } from '@/theme';

export const ChatWelcome: React.FC = () => {
  const { colors } = useTheme();
  
  // 找回原版情绪循环逻辑
  const [mood, setMood] = useState<'neutral' | 'happy' | 'thinking'>('happy');

  useEffect(() => {
    const interval = setInterval(() => {
      const moods: Array<'neutral' | 'happy' | 'thinking'> = ['neutral', 'happy', 'thinking'];
      setMood(moods[Math.floor(Math.random() * moods.length)]);
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  // 极简入场动画（不影响原有布局）
  const opacity = useSharedValue(0);
  useEffect(() => {
    opacity.value = withTiming(1, { duration: 800 });
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
  }));

  return (
    <Animated.View style={[styles.welcomeContainer, animatedStyle]}>
      {/* 找回原版元素 */}
      <WoodenRobot primaryColor={colors.primary} mood={mood} />
      
      <Text variant="headlineSmall" style={[styles.welcomeTitle, { color: colors.primary }]}>
        EvoLoop AI
      </Text>
      
      {/* 找回原版文案 */}
      <Text variant="bodyMedium" style={[styles.welcomeSubtitle, { color: colors.onSurfaceVariant }]}>
        你好！我是你的木头机器人助手
      </Text>
      
      <Text variant="bodySmall" style={[styles.welcomeHint, { color: colors.onSurfaceVariant }]}>
        点击麦克风开始语音对话
      </Text>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  // 找回原版布局样式
  welcomeContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 32,
    // 原版使用 gap: 16 (在 React Native 0.71+ 支持)
    gap: 16,
  },
  welcomeTitle: {
    fontWeight: 'bold',
    marginTop: 16,
  },
  welcomeSubtitle: {
    fontSize: 16,
    fontWeight: '500',
  },
  welcomeHint: {
    marginTop: 4,
    opacity: 0.6,
  },
});
