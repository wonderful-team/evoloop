import React from 'react';
import { View, StyleSheet, Image, TouchableOpacity, Linking } from 'react-native';
import { Text, Surface } from 'react-native-paper';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import { MessageAttachment } from '@/types/conversation';
import { useTheme } from '@/theme';

interface MessageAttachmentsProps {
  attachments: MessageAttachment[];
  isUser: boolean;
}

export function MessageAttachments({ attachments, isUser }: MessageAttachmentsProps) {
  const { colors } = useTheme();

  if (!attachments || attachments.length === 0) return null;

  const images = attachments.filter(a => a.type === 'image');
  const files = attachments.filter(a => a.type === 'file' || a.type === 'audio' || a.type === 'reference');

  const handleOpenAttachment = (url: string) => {
    if (url) {
      Linking.openURL(url).catch(err => console.error('Failed to open URL:', err));
    }
  };

  return (
    <View style={styles.container}>
      {/* 图片展示 */}
      {images.length > 0 && (
        <View style={styles.imageGrid}>
          {images.map((img) => (
            <TouchableOpacity 
              key={img.id} 
              onPress={() => handleOpenAttachment(img.url)}
              activeOpacity={0.9}
            >
              <Image 
                source={{ uri: img.url }} 
                style={styles.imageThumbnail}
                resizeMode="cover"
              />
            </TouchableOpacity>
          ))}
        </View>
      )}

      {/* 文件展示 */}
      {files.length > 0 && (
        <View style={styles.fileList}>
          {files.map((file) => (
            <Surface 
              key={file.id} 
              style={[
                styles.fileItem, 
                { backgroundColor: isUser ? 'rgba(255,255,255,0.1)' : colors.surfaceVariant }
              ]}
              elevation={0}
            >
              <TouchableOpacity 
                style={styles.fileButton}
                onPress={() => handleOpenAttachment(file.url)}
              >
                <MaterialCommunityIcons 
                  name={file.type === 'audio' ? 'volume-high' : 'file-document-outline'} 
                  size={24} 
                  color={isUser ? '#fff' : colors.primary} 
                />
                <View style={styles.fileInfo}>
                  <Text 
                    variant="bodyMedium" 
                    style={[styles.fileName, { color: isUser ? '#fff' : colors.onSurface }]}
                    numberOfLines={1}
                  >
                    {file.name}
                  </Text>
                  {file.metadata?.duration && (
                    <Text variant="labelSmall" style={{ color: isUser ? 'rgba(255,255,255,0.7)' : colors.onSurfaceVariant }}>
                      {Math.round(file.metadata.duration / 1000)}s
                    </Text>
                  )}
                </View>
                <MaterialCommunityIcons 
                  name="download" 
                  size={18} 
                  color={isUser ? 'rgba(255,255,255,0.5)' : colors.onSurfaceVariant} 
                />
              </TouchableOpacity>
            </Surface>
          ))}
        </View>
      )}
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
  fileList: {
    gap: 8,
  },
  fileItem: {
    borderRadius: 8,
    overflow: 'hidden',
  },
  fileButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
  },
  fileInfo: {
    flex: 1,
    marginLeft: 10,
  },
  fileName: {
    fontWeight: '500',
  },
});
