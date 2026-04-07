// 骨架屏列表组件

import React from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { useTheme } from '@/theme';

interface SkeletonItemProps {
  width?: number | string;
  height?: number;
  borderRadius?: number;
}

function SkeletonItem({
  width = '100%',
  height = 20,
  borderRadius = 4,
}: SkeletonItemProps) {
  const { colors } = useTheme();
  const shimmerAnim = React.useRef(new Animated.Value(0)).current;

  React.useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmerAnim, {
          toValue: 1,
          duration: 1000,
          useNativeDriver: true,
        }),
        Animated.timing(shimmerAnim, {
          toValue: 0,
          duration: 1000,
          useNativeDriver: true,
        }),
      ])
    );
    animation.start();
    return () => animation.stop();
  }, [shimmerAnim]);

  const opacity = shimmerAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0.3, 0.7],
  });

  return (
    <Animated.View
      style={[
        styles.skeleton,
        {
          width,
          height,
          borderRadius,
          backgroundColor: colors.surfaceVariant,
          opacity,
        },
      ]}
    />
  );
}

interface SkeletonListProps {
  count?: number;
  type?: 'list' | 'card' | 'chat';
}

export function SkeletonList({ count = 5, type = 'list' }: SkeletonListProps) {
  const { colors } = useTheme();

  const renderListItem = (index: number) => (
    <View key={index} style={[styles.listItem, { borderBottomColor: colors.outlineVariant }]}>
      <SkeletonItem width={48} height={48} borderRadius={24} />
      <View style={styles.listContent}>
        <SkeletonItem width="60%" height={16} />
        <SkeletonItem width="80%" height={12} />
      </View>
    </View>
  );

  const renderCardItem = (index: number) => (
    <View
      key={index}
      style={[styles.cardItem, { backgroundColor: colors.surface, borderColor: colors.outlineVariant }]}
    >
      <SkeletonItem width="100%" height={120} borderRadius={8} />
      <View style={styles.cardContent}>
        <SkeletonItem width="70%" height={18} />
        <SkeletonItem width="100%" height={14} />
        <SkeletonItem width="50%" height={14} />
      </View>
    </View>
  );

  const renderChatItem = (index: number) => {
    const isUser = index % 2 === 0;
    return (
      <View
        key={index}
        style={[
          styles.chatItem,
          isUser ? styles.chatItemUser : styles.chatItemAssistant,
        ]}
      >
        {!isUser && <SkeletonItem width={32} height={32} borderRadius={16} />}
        <View style={[styles.chatBubble, { maxWidth: '70%' }]}>
          <SkeletonItem
            width={Math.random() * 100 + 100}
            height={Math.random() * 40 + 40}
            borderRadius={12}
          />
        </View>
        {isUser && <SkeletonItem width={32} height={32} borderRadius={16} />}
      </View>
    );
  };

  const renderItem = (index: number) => {
    switch (type) {
      case 'card':
        return renderCardItem(index);
      case 'chat':
        return renderChatItem(index);
      default:
        return renderListItem(index);
    }
  };

  return (
    <View style={styles.container}>
      {Array.from({ length: count }, (_, i) => renderItem(i))}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  skeleton: {
    overflow: 'hidden',
  },
  listItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  listContent: {
    flex: 1,
    gap: 8,
  },
  cardItem: {
    margin: 16,
    marginBottom: 0,
    borderRadius: 12,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  cardContent: {
    padding: 16,
    gap: 8,
  },
  chatItem: {
    flexDirection: 'row',
    padding: 8,
    gap: 8,
  },
  chatItemUser: {
    justifyContent: 'flex-end',
  },
  chatItemAssistant: {
    justifyContent: 'flex-start',
  },
  chatBubble: {
    marginHorizontal: 8,
  },
});

// 全屏骨架屏
export function SkeletonScreen() {
  const { colors } = useTheme();

  return (
    <View style={[styles.screen, { backgroundColor: colors.background }]}>
      {/* 头部骨架 */}
      <View style={[styles.header, { borderBottomColor: colors.outlineVariant }]}>
        <SkeletonItem width={120} height={24} />
        <SkeletonItem width={40} height={40} borderRadius={20} />
      </View>

      {/* 内容骨架 */}
      <SkeletonList count={6} type="list" />
    </View>
  );
}

const screenStyles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
});

Object.assign(styles, screenStyles);
