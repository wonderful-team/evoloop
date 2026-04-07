// 通用头部导航组件

import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Appbar, Text, IconButton } from 'react-native-paper';
import { useTheme } from '@/theme';
import { useRouter } from 'expo-router';

interface HeaderProps {
  title: string;
  subtitle?: string;
  showBack?: boolean;
  onBack?: () => void;
  rightAction?: {
    icon: string;
    onPress: () => void;
  };
  rightActions?: Array<{
    icon: string;
    onPress: () => void;
  }>;
}

export function Header({
  title,
  subtitle,
  showBack = false,
  onBack,
  rightAction,
  rightActions,
}: HeaderProps) {
  const { colors } = useTheme();
  const router = useRouter();

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      router.back();
    }
  };

  return (
    <Appbar.Header style={[styles.header, { backgroundColor: colors.background }]}>
      {showBack && (
        <Appbar.BackAction color={colors.text.primary} onPress={handleBack} />
      )}

      <View style={styles.titleContainer}>
        <Text variant="titleMedium" style={[styles.title, { color: colors.text.primary }]}>
          {title}
        </Text>
        {subtitle && (
          <Text variant="bodySmall" style={{ color: colors.text.secondary }}>
            {subtitle}
          </Text>
        )}
      </View>

      {rightAction && (
        <Appbar.Action
          icon={rightAction.icon}
          color={colors.text.primary}
          onPress={rightAction.onPress}
        />
      )}

      {rightActions?.map((action, index) => (
        <Appbar.Action
          key={index}
          icon={action.icon}
          color={colors.text.primary}
          onPress={action.onPress}
        />
      ))}
    </Appbar.Header>
  );
}

const styles = StyleSheet.create({
  header: {
    elevation: 0,
    shadowOpacity: 0,
  },
  titleContainer: {
    flex: 1,
    justifyContent: 'center',
  },
  title: {
    fontWeight: '600',
  },
});
