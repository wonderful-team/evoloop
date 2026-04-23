// Toast 通知组件

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated, Dimensions } from 'react-native';
import { Text, IconButton } from 'react-native-paper';
import { useTheme } from '@/theme';

const { width } = Dimensions.get('window');

export type ToastType = 'success' | 'error' | 'warning' | 'info';

interface ToastProps {
  visible: boolean;
  message: string;
  type?: ToastType;
  duration?: number;
  onDismiss?: () => void;
  action?: {
    label: string;
    onPress: () => void;
  };
}

export function Toast({
  visible,
  message,
  type = 'info',
  duration = 3000,
  onDismiss,
  action,
}: ToastProps) {
  const { colors } = useTheme();
  const translateY = useRef(new Animated.Value(-100)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      // 显示动画
      Animated.parallel([
        Animated.timing(translateY, {
          toValue: 0,
          duration: 300,
          useNativeDriver: true,
        }),
        Animated.timing(opacity, {
          toValue: 1,
          duration: 300,
          useNativeDriver: true,
        }),
      ]).start();

      // 自动隐藏
      if (duration > 0) {
        const timer = setTimeout(() => {
          hide();
        }, duration);
        return () => clearTimeout(timer);
      }
    } else {
      hide();
    }
  }, [visible, duration]);

  const hide = () => {
    Animated.parallel([
      Animated.timing(translateY, {
        toValue: -100,
        duration: 200,
        useNativeDriver: true,
      }),
      Animated.timing(opacity, {
        toValue: 0,
        duration: 200,
        useNativeDriver: true,
      }),
    ]).start(() => {
      onDismiss?.();
    });
  };

  const getIcon = () => {
    switch (type) {
      case 'success':
        return 'check-circle';
      case 'error':
        return 'alert-circle';
      case 'warning':
        return 'alert';
      default:
        return 'information';
    }
  };

  const getColors = () => {
    switch (type) {
      case 'success':
        return {
          background: colors.status.success + '20',
          icon: colors.status.success,
        };
      case 'error':
        return {
          background: colors.status.error + '20',
          icon: colors.status.error,
        };
      case 'warning':
        return {
          background: colors.status.warning + '20',
          icon: colors.status.warning,
        };
      default:
        return {
          background: colors.status.info + '20',
          icon: colors.status.info,
        };
    }
  };

  const toastColors = getColors();

  if (!visible) return null;

  return (
    <Animated.View
      style={[
        styles.container,
        {
          backgroundColor: toastColors.background,
          transform: [{ translateY }],
          opacity,
        },
      ]}
    >
      <View style={styles.content}>
        <IconButton
          icon={getIcon()}
          size={20}
          iconColor={toastColors.icon}
          style={styles.icon}
        />
        <Text
          variant="bodyMedium"
          style={[styles.message, { color: colors.text.primary }]}
          numberOfLines={2}
        >
          {message}
        </Text>
        {action && (
          <Text
            variant="labelLarge"
            style={[styles.action, { color: colors.primary }]}
            onPress={action.onPress}
          >
            {action.label}
          </Text>
        )}
        <IconButton
          icon="close"
          size={16}
          iconColor={colors.text.secondary}
          onPress={hide}
          style={styles.closeButton}
        />
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 60,
    left: 16,
    right: 16,
    borderRadius: 12,
    zIndex: 9999,
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    minHeight: 48,
  },
  icon: {
    margin: 0,
  },
  message: {
    flex: 1,
    marginHorizontal: 4,
  },
  action: {
    marginRight: 8,
    fontWeight: '600',
  },
  closeButton: {
    margin: 0,
  },
});

// Toast Hook
import { useState, useCallback } from 'react';

interface ToastState {
  visible: boolean;
  message: string;
  type: ToastType;
  action?: { label: string; onPress: () => void };
}

export function useToast() {
  const [state, setState] = useState<ToastState>({
    visible: false,
    message: '',
    type: 'info',
  });

  const show = useCallback(
    (message: string, type: ToastType = 'info', action?: { label: string; onPress: () => void }) => {
      setState({ visible: true, message, type, action });
    },
    []
  );

  const hide = useCallback(() => {
    setState((prev) => ({ ...prev, visible: false }));
  }, []);

  const success = useCallback(
    (message: string, action?: { label: string; onPress: () => void }) => {
      show(message, 'success', action);
    },
    [show]
  );

  const error = useCallback(
    (message: string, action?: { label: string; onPress: () => void }) => {
      show(message, 'error', action);
    },
    [show]
  );

  const warning = useCallback(
    (message: string, action?: { label: string; onPress: () => void }) => {
      show(message, 'warning', action);
    },
    [show]
  );

  const info = useCallback(
    (message: string, action?: { label: string; onPress: () => void }) => {
      show(message, 'info', action);
    },
    [show]
  );

  return {
    ...state,
    show,
    hide,
    success,
    error,
    warning,
    info,
  };
}
