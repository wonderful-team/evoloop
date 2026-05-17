// 引用标签展示栏 - 从 VoiceInput 中提取的纯展示组件

import React from 'react';
import { View, StyleSheet, ScrollView } from 'react-native';
import { ResourceChip } from '@/components/chat';
import { MessageReference } from '@/types/conversation';

interface VoiceInputReferencesBarProps {
  references: MessageReference[];
  onRemove: (index: number) => void;
}

export function VoiceInputReferencesBar({ references, onRemove }: VoiceInputReferencesBarProps) {
  if (references.length === 0) return null;

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={styles.container}
      contentContainerStyle={styles.content}
    >
      {references.map((ref, index) => (
        <ResourceChip
          key={ref.id}
          reference={ref}
          onRemove={() => onRemove(index)}
          compact
        />
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    maxHeight: 48,
    marginHorizontal: 8,
    marginBottom: 4,
  },
  content: {
    paddingHorizontal: 4,
    gap: 8,
    alignItems: 'center',
  },
});
