// Snackbar 底部提示组件

import React, { useEffect, useRef } from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { Text, Button } from 'react-native-paper';
import { useTheme } from '@/theme';

export type SnackbarType = 'success' | 'error' | 'warning' | 'info';

interface SnackbarProps {
  visible: boolean;
  message: string;
  type?: SnackbarType;
  duration?: number;
  onDismiss?: () => void;
  action?: {
    label: string;
    onPress: () => void;
  };
}

export function Snackbar({
  visible,
  message,
  type = 'info',
  duration = 3000,
  onDismiss,
  action,
}: SnackbarProps) {
  const { colors } = useTheme();
  const translateY = useRef(new Animated.Value(100)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
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
        toValue: 100,
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

  const getBackgroundColor = () => {
    switch (type) {
      case 'success':
        return colors.status.success;
      case 'error':
        return colors.status.error;
      case 'warning':
        return colors.status.warning;
      default:
        return colors.surfaceVariant;
    }
  };

  const getTextColor = () => {
    switch (type) {
      case 'success':
      case 'error':
        return '#FFFFFF';
      case 'warning':
        return '#000000';
      default:
        return colors.text.primary;
    }
  };

  if (!visible) return null;

  return (
    <Animated.View
      style={[
        styles.container,
        {
          backgroundColor: getBackgroundColor(),
          transform: [{ translateY }],
          opacity,
        },
      ]}
    >
      <Text
        variant="bodyMedium"
        style={[styles.message, { color: getTextColor() }]}
        numberOfLines={2}
      >
        {message}
      </Text>
      {action && (
        <Button
          mode="text"
          onPress={() => {
            action.onPress();
            hide();
          }}
          textColor={getTextColor()}
          style={styles.action}
        >
          {action.label}
        </Button>
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    bottom: 24,
    left: 16,
    right: 16,
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 8,
    elevation: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    zIndex: 9999,
  },
  message: {
    flex: 1,
  },
  action: {
    marginLeft: 8,
  },
});

// Snackbar Hook
import { useState, useCallback } from 'react';

interface SnackbarState {
  visible: boolean;
  message: string;
  type: SnackbarType;
  action?: { label: string; onPress: () => void };
}

export function useSnackbar() {
  const [state, setState] = useState<SnackbarState>({
    visible: false,
    message: '',
    type: 'info',
  });

  const show = useCallback(
    (message: string, type: SnackbarType = 'info', action?: { label: string; onPress: () => void }) => {
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
