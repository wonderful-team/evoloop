// 通用头部导航组件

import React from 'react';
import { View, StyleSheet, TouchableOpacity } from 'react-native';
import { Text } from 'react-native-paper';
import { useTheme } from '@/theme';
import { router as navigationRouter } from '@/utils/navigation';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

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

  const handleBack = () => {
    if (onBack) {
      onBack();
    } else {
      navigationRouter.back();
    }
  };

  const hasRight = !!rightAction || (rightActions && rightActions.length > 0);

  return (
    <View style={[styles.header, { backgroundColor: colors.background }]}>
      {/* 左侧 */}
      <View style={styles.side}>
        {showBack && (
          <TouchableOpacity onPress={handleBack} style={styles.iconButton}>
            <MaterialIcons name="arrow-back" size={24} color={colors.text.primary} />
          </TouchableOpacity>
        )}
      </View>

      {/* 中间标题 */}
      <View style={styles.titleContainer}>
        <Text
          variant="titleMedium"
          style={[styles.title, { color: colors.text.primary }]}
          numberOfLines={1}
        >
          {title}
        </Text>
        {subtitle && (
          <Text
            variant="bodySmall"
            style={{ color: colors.text.secondary }}
            numberOfLines={1}
          >
            {subtitle}
          </Text>
        )}
      </View>

      {/* 右侧 */}
      <View style={[styles.side, styles.sideRight]}>
        {rightAction && (
          <TouchableOpacity onPress={rightAction.onPress} style={styles.iconButton}>
            <MaterialIcons name={rightAction.icon as any} size={24} color={colors.text.primary} />
          </TouchableOpacity>
        )}
        {rightActions?.map((action, index) => (
          <TouchableOpacity key={index} onPress={action.onPress} style={styles.iconButton}>
            <MaterialIcons name={action.icon as any} size={24} color={colors.text.primary} />
          </TouchableOpacity>
        ))}
        {/* 当左侧有按钮而右侧没有时，加一个等宽占位，保证标题绝对居中 */}
        {showBack && !hasRight && <View style={styles.iconButton} />}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 56,
    paddingHorizontal: 4,
    elevation: 0,
    shadowOpacity: 0,
  },
  side: {
    minWidth: 48,
    flexDirection: 'row',
    alignItems: 'center',
  },
  sideRight: {
    justifyContent: 'flex-end',
  },
  titleContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontWeight: '600',
    textAlign: 'center',
  },
  iconButton: {
    width: 48,
    height: 48,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
