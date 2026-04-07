// 卡片组件

import React from 'react';
import { View, StyleSheet, ViewStyle, TouchableOpacity } from 'react-native';
import { Card as PaperCard, Text, IconButton } from 'react-native-paper';
import { useTheme } from 'react-native-paper';

interface CardProps {
  title?: string;
  subtitle?: string;
  children: React.ReactNode;
  onPress?: () => void;
  style?: ViewStyle;
  rightIcon?: string;
  onRightIconPress?: () => void;
  disabled?: boolean;
}

export function Card({
  title,
  subtitle,
  children,
  onPress,
  style,
  rightIcon,
  onRightIconPress,
  disabled = false,
}: CardProps) {
  const theme = useTheme();

  const content = (
    <View style={[styles.container, style]}>
      {(title || subtitle || rightIcon) && (
        <View style={styles.header}>
          <View style={styles.titleContainer}>
            {title && (
              <Text variant="titleMedium" style={styles.title}>
                {title}
              </Text>
            )}
            {subtitle && (
              <Text variant="bodySmall" style={styles.subtitle}>
                {subtitle}
              </Text>
            )}
          </View>
          {rightIcon && (
            <IconButton
              icon={rightIcon}
              size={20}
              onPress={onRightIconPress}
              iconColor={theme.colors.onSurfaceVariant}
            />
          )}
        </View>
      )}
      <View style={styles.content}>{children}</View>
    </View>
  );

  if (onPress) {
    return (
      <TouchableOpacity
        onPress={onPress}
        disabled={disabled}
        activeOpacity={0.7}
        style={styles.touchable}
      >
        {content}
      </TouchableOpacity>
    );
  }

  return <PaperCard style={styles.card}>{content}</PaperCard>;
}

const styles = StyleSheet.create({
  card: {
    margin: 0,
    elevation: 2,
  },
  touchable: {
    marginVertical: 8,
  },
  container: {
    padding: 16,
    backgroundColor: '#fff',
    borderRadius: 12,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  titleContainer: {
    flex: 1,
  },
  title: {
    fontWeight: '600',
  },
  subtitle: {
    opacity: 0.6,
    marginTop: 2,
  },
  content: {
    marginTop: 4,
  },
});
