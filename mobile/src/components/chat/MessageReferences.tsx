import React, { useState } from 'react';
import { View, StyleSheet, Image, TouchableOpacity, Linking, useWindowDimensions } from 'react-native';
import { MessageReference } from '@/types/conversation';
import { useGlobalToast } from '@/contexts/ToastContext';
import { BASE_URL } from '@/constants/config';
import { ResourceChip } from './ResourceChip';
import { ImageViewer } from './MessageContent';

interface MessageReferencesProps {
  references: MessageReference[];
  isUser: boolean;
}

export function MessageReferences({ references, isUser }: MessageReferencesProps) {
  const toast = useGlobalToast();
  const { width: screenWidth } = useWindowDimensions();
  const [viewerVisible, setViewerVisible] = useState(false);
  const [activeImageUrl, setActiveImageUrl] = useState('');

  if (!references || references.length === 0) return null;

  const images = references.filter(a => a.type === 'image');
  const files = references.filter(a => a.type === 'file' || a.type === 'audio');

  const imageWidth = (screenWidth - 48 - 16) / 3; // 48 for paddings/margins (12*2 margin in ChatScreen + 12*2 padding in MessageList), 16 for gaps

  const handleOpenReference = (url: string) => {
    if (!url) return;
    let finalUrl = url;
    if (url.startsWith('/api/')) {
      finalUrl = `${BASE_URL}${url}`;
    }
    if (finalUrl.startsWith('http://') || finalUrl.startsWith('https://')) {
      Linking.openURL(finalUrl).catch(err => console.error('Failed to open URL:', err));
    } else if (finalUrl.startsWith('file://') || finalUrl.startsWith('/') || finalUrl.startsWith('./')) {
      toast.warning('该文件为工作机本地工作区文件，暂不支持在移动端直接预览');
    } else {
      console.log('Ignore opening non-HTTP reference:', finalUrl);
    }
  };

  const handleOpenImage = (url: string) => {
    let finalUrl = url;
    if (url && url.startsWith('/api/')) {
      finalUrl = `${BASE_URL}${url}`;
    }
    setActiveImageUrl(finalUrl);
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
                source={{ uri: img.target_id?.startsWith('/api/') ? `${BASE_URL}${img.target_id}` : img.target_id }}
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
});
