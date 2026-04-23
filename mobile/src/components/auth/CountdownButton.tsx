// 倒计时按钮组件 - 用于获取验证码

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { StyleSheet } from 'react-native';
import { Button } from 'react-native-paper';
import { useTheme } from '@/theme';

interface CountdownButtonProps {
  onPress: () => Promise<void> | void;
  disabled?: boolean;
  initialSeconds?: number;
  label?: string;
  countdownLabel?: (seconds: number) => string;
}

export function CountdownButton({
  onPress,
  disabled = false,
  initialSeconds = 120,
  label = '获取验证码',
  countdownLabel = (seconds) => `${seconds}s后重试`,
}: CountdownButtonProps) {
  const { colors } = useTheme();
  const [countdown, setCountdown] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // 清理定时器
  useEffect(() => {
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, []);

  // 开始倒计时
  const startCountdown = useCallback((seconds: number) => {
    setCountdown(seconds);
    
    timerRef.current = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }, []);

  // 处理点击
  const handlePress = useCallback(async () => {
    if (countdown > 0 || isLoading || disabled) return;

    setIsLoading(true);
    try {
      await onPress();
      startCountdown(initialSeconds);
    } finally {
      setIsLoading(false);
    }
  }, [onPress, countdown, isLoading, disabled, initialSeconds, startCountdown]);

  const isDisabled = countdown > 0 || isLoading || disabled;

  return (
    <Button
      mode="outlined"
      onPress={handlePress}
      disabled={isDisabled}
      loading={isLoading}
      style={styles.button}
      contentStyle={styles.content}
      labelStyle={[
        styles.label,
        {
          color: isDisabled ? colors.text.disabled : colors.primary,
        },
      ]}
    >
      {countdown > 0 ? countdownLabel(countdown) : label}
    </Button>
  );
}

const styles = StyleSheet.create({
  button: {
    width: 100,
    borderRadius: 8,
  },
  content: {
    height: 44,
  },
  label: {
    fontSize: 13,
    fontWeight: '500',
    marginHorizontal: 0,
  },
});
