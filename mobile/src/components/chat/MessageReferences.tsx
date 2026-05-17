import React, { useState } from 'react';
import { View, StyleSheet, Image, TouchableOpacity, Linking, useWindowDimensions } from 'react-native';
import { Text } from 'react-native-paper';
import { MessageReference } from '@/types/conversation';
import { useTheme } from '@/theme';
import { ResourceChip } from './ResourceChip';
import { ImageViewer } from './MessageContent';

interface MessageReferencesProps {
  references: MessageReference[];
  isUser: boolean;
}

export function MessageReferences({ references, isUser }: MessageReferencesProps) {
  const { colors } = useTheme();
  const { width: screenWidth } = useWindowDimensions();
  const [viewerVisible, setViewerVisible] = useState(false);
  const [activeImageUrl, setActiveImageUrl] = useState('');

  if (!references || references.length === 0) return null;

  const images = references.filter(a => a.type === 'image');
  const files = references.filter(a => a.type === 'file' || a.type === 'audio');

  const imageWidth = (screenWidth - 48 - 16) / 3; // 48 for paddings/margins (12*2 margin in ChatScreen + 12*2 padding in MessageList), 16 for gaps

  const handleOpenReference = (url: string) => {
    if (url && (url.startsWith('http://') || url.startsWith('https://'))) {
      Linking.openURL(url).catch(err => console.error('Failed to open URL:', err));
    } else {
      console.log('Ignore opening non-HTTP reference:', url);
    }
  };

  const handleOpenImage = (url: string) => {
    setActiveImageUrl(url);
    setViewerVisible(true);
  };

  return (
    <View style={styles.container}>
      {/* 图片展示 */}
      {images.length > 0 && (
        <View style={styles.imageGrid}>
          {images.map((img) => (
            <TouchableOpacity 
              key={img.id} 
              onPress={() => handleOpenImage(img.target_id)}
              activeOpacity={0.9}
            >
              <Image 
                source={{ uri: img.target_id }} 
                style={[styles.imageThumbnail, { width: imageWidth, height: imageWidth }]}
                resizeMode="cover"
              />
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* 文件展示 */}
      {files.length > 0 && (
        <View style={styles.chipList}>
          {files.map((file) => (
            <TouchableOpacity 
              key={file.id} 
              onPress={() => handleOpenReference(file.target_id)}
            >
              <ResourceChip reference={file} compact={true} isUser={isUser} />
            </TouchableOpacity>
          ))}
        </View>
      )}
      <ImageViewer 
        uri={activeImageUrl} 
        visible={viewerVisible} 
        onClose={() => setViewerVisible(false)} 
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginTop: 8,
    width: '100%',
  },
  imageGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 4,
  },
  imageThumbnail: {
    width: 120,
    height: 120,
    borderRadius: 8,
    backgroundColor: '#eee',
  },
  chipList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  imageThumbnail: {
    width: 120,
    height: 120,
    borderRadius: 8,
    backgroundColor: '#eee',
  },
});
