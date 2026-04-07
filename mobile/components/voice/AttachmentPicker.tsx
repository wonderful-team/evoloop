// 附件选择组件 - 支持图片选择和相机拍照

import React, { useCallback, useState } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Image,
  Modal,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { Text, IconButton } from 'react-native-paper';
import { MaterialIcons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useTheme } from '@/theme';
import { uploadChatImage, ChatAttachment } from '@/services/api/upload';

export { type ChatAttachment } from '@/services/api/upload';

export interface Attachment {
  id: string;
  type: 'image';
  uri: string;
  name?: string;
  mimeType?: string;
  size?: number;
  uploading?: boolean;
  uploaded?: boolean;
  url?: string;
}

interface AttachmentPickerProps {
  attachments: Attachment[];
  onAttachmentsChange: (attachments: Attachment[]) => void;
  maxAttachments?: number;
  onUploadComplete?: (attachments: ChatAttachment[]) => void;
}

export function AttachmentPicker({
  attachments,
  onAttachmentsChange,
  maxAttachments = 5,
  onUploadComplete,
}: AttachmentPickerProps) {
  const { colors } = useTheme();
  const [showOptions, setShowOptions] = useState(false);
  const [uploading, setUploading] = useState(false);

  // 请求相机权限
  const requestCameraPermission = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    return status === 'granted';
  }, []);

  // 请求相册权限
  const requestMediaLibraryPermission = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    return status === 'granted';
  }, []);

  // 上传单个图片
  const uploadSingleImage = useCallback(async (attachment: Attachment): Promise<Attachment> => {
    try {
      // 更新上传状态
      onAttachmentsChange(
        attachments.map(att =>
          att.id === attachment.id ? { ...att, uploading: true } : att
        )
      );

      // 上传图片
      const result = await uploadChatImage(attachment.uri);

      // 更新上传成功状态
      const updatedAttachment: Attachment = {
        ...attachment,
        uploading: false,
        uploaded: true,
        url: result.url,
      };

      onAttachmentsChange(
        attachments.map(att =>
          att.id === attachment.id ? updatedAttachment : att
        )
      );

      return updatedAttachment;
    } catch (error) {
      // 更新上传失败状态
      onAttachmentsChange(
        attachments.map(att =>
          att.id === attachment.id ? { ...att, uploading: false, uploaded: false } : att
        )
      );
      throw error;
    }
  }, [attachments, onAttachmentsChange]);

  // 处理图片选择
  const handleImagePick = useCallback(async () => {
    setShowOptions(false);

    if (attachments.length >= maxAttachments) {
      Alert.alert('提示', `最多只能选择 ${maxAttachments} 张图片`);
      return;
    }

    const hasPermission = await requestMediaLibraryPermission();
    if (!hasPermission) {
      Alert.alert('权限不足', '需要访问相册权限才能选择图片');
      return;
    }

    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsMultipleSelection: true,
        quality: 0.8,
        selectionLimit: maxAttachments - attachments.length,
      });

      if (!result.canceled && result.assets) {
        const newAttachments: Attachment[] = result.assets.map((asset, index) => ({
          id: `img_${Date.now()}_${index}`,
          type: 'image',
          uri: asset.uri,
          name: asset.fileName || `image_${Date.now()}_${index}.jpg`,
          mimeType: asset.mimeType || 'image/jpeg',
          size: asset.fileSize,
          uploading: false,
          uploaded: false,
        }));

        onAttachmentsChange([...attachments, ...newAttachments]);
        
        // 自动开始上传
        setUploading(true);
        const uploadedAttachments: ChatAttachment[] = [];
        
        for (const attachment of newAttachments) {
          try {
            const uploaded = await uploadSingleImage(attachment);
            if (uploaded.url) {
              uploadedAttachments.push({
                type: 'image',
                url: uploaded.url,
                name: uploaded.name || '',
                ext: uploaded.name?.split('.').pop() || 'jpg',
              });
            }
          } catch (error: any) {
            console.error('上传图片失败:', error);
            Alert.alert('上传失败', error.message || '图片上传失败，请重试');
          }
        }
        
        setUploading(false);
        
        if (uploadedAttachments.length > 0) {
          onUploadComplete?.(uploadedAttachments);
        }
      }
    } catch (error: any) {
      console.error('选择图片失败:', error);
      Alert.alert('错误', '选择图片失败，请重试');
      setUploading(false);
    }
  }, [attachments, maxAttachments, onAttachmentsChange, onUploadComplete, requestMediaLibraryPermission, uploadSingleImage]);

  // 处理相机拍照
  const handleCamera = useCallback(async () => {
    setShowOptions(false);

    if (attachments.length >= maxAttachments) {
      Alert.alert('提示', `最多只能选择 ${maxAttachments} 张图片`);
      return;
    }

    const hasPermission = await requestCameraPermission();
    if (!hasPermission) {
      Alert.alert('权限不足', '需要相机权限才能拍照');
      return;
    }

    try {
      const result = await ImagePicker.launchCameraAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.8,
      });

      if (!result.canceled && result.assets) {
        const newAttachment: Attachment = {
          id: `camera_${Date.now()}`,
          type: 'image',
          uri: result.assets[0].uri,
          name: result.assets[0].fileName || `camera_${Date.now()}.jpg`,
          mimeType: result.assets[0].mimeType || 'image/jpeg',
          size: result.assets[0].fileSize,
          uploading: false,
          uploaded: false,
        };

        onAttachmentsChange([...attachments, newAttachment]);
        
        // 自动开始上传
        setUploading(true);
        
        try {
          const uploaded = await uploadSingleImage(newAttachment);
          if (uploaded.url) {
            onUploadComplete?.([{
              type: 'image',
              url: uploaded.url,
              name: uploaded.name || '',
              ext: uploaded.name?.split('.').pop() || 'jpg',
            }]);
          }
        } catch (error: any) {
          console.error('上传照片失败:', error);
          Alert.alert('上传失败', error.message || '照片上传失败，请重试');
        } finally {
          setUploading(false);
        }
      }
    } catch (error: any) {
      console.error('拍照失败:', error);
      Alert.alert('错误', '拍照失败，请重试');
      setUploading(false);
    }
  }, [attachments, maxAttachments, onAttachmentsChange, onUploadComplete, requestCameraPermission, uploadSingleImage]);

  // 移除附件
  const removeAttachment = useCallback((id: string) => {
    onAttachmentsChange(attachments.filter(att => att.id !== id));
  }, [attachments, onAttachmentsChange]);

  // 显示选项弹窗
  const showPickerOptions = useCallback(() => {
    setShowOptions(true);
  }, []);

  // 隐藏选项弹窗
  const hidePickerOptions = useCallback(() => {
    setShowOptions(false);
  }, []);

  return (
    <View style={styles.container}>
      {/* 附件预览列表 */}
      {attachments.length > 0 && (
        <View style={styles.attachmentList}>
          {attachments.map((att) => (
            <View key={att.id} style={styles.attachmentItem}>
              <Image source={{ uri: att.uri }} style={styles.attachmentImage} />
              
              {/* 上传中遮罩 */}
              {att.uploading && (
                <View style={styles.uploadingOverlay}>
                  <ActivityIndicator size="small" color="#fff" />
                </View>
              )}
              
              {/* 上传失败标记 */}
              {!att.uploading && att.uploaded === false && (
                <View style={styles.errorOverlay}>
                  <MaterialIcons name="error" size={20} color="#fff" />
                </View>
              )}
              
              {/* 删除按钮 */}
              {!att.uploading && (
                <TouchableOpacity
                  style={[styles.removeButton, { backgroundColor: colors.error }]}
                  onPress={() => removeAttachment(att.id)}
                >
                  <MaterialIcons name="close" size={14} color="#fff" />
                </TouchableOpacity>
              )}
            </View>
          ))}
          
          {/* 添加更多按钮 */}
          {attachments.length < maxAttachments && !uploading && (
            <TouchableOpacity
              style={[styles.addButton, { borderColor: colors.outline }]}
              onPress={showPickerOptions}
            >
              <MaterialIcons name="add" size={24} color={colors.outline} />
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* 底部工具栏 */}
      {attachments.length === 0 && (
        <View style={styles.toolbar}>
          <TouchableOpacity
            style={styles.toolbarButton}
            onPress={showPickerOptions}
            disabled={uploading}
          >
            <MaterialIcons 
              name="image" 
              size={22} 
              color={uploading ? colors.outline : colors.onSurfaceVariant} 
            />
          </TouchableOpacity>
          
          <TouchableOpacity
            style={styles.toolbarButton}
            onPress={handleCamera}
            disabled={uploading}
          >
            <MaterialIcons 
              name="camera-alt" 
              size={22} 
              color={uploading ? colors.outline : colors.onSurfaceVariant} 
            />
          </TouchableOpacity>
          
          <TouchableOpacity style={styles.toolbarButton}>
            <MaterialIcons name="folder" size={22} color={colors.onSurfaceVariant} />
          </TouchableOpacity>
        </View>
      )}

      {/* 选项弹窗 */}
      <Modal
        visible={showOptions}
        transparent
        animationType="slide"
        onRequestClose={hidePickerOptions}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={hidePickerOptions}
        >
          <View style={[styles.modalContent, { backgroundColor: colors.surface }]}>
            <Text variant="titleMedium" style={styles.modalTitle}>
              选择附件
            </Text>
            
            <TouchableOpacity
              style={styles.optionButton}
              onPress={handleImagePick}
              disabled={uploading}
            >
              <MaterialIcons name="image" size={24} color={colors.primary} />
              <Text variant="bodyLarge" style={[styles.optionText, { color: colors.onSurface }]}>
                从相册选择
              </Text>
              {uploading && <ActivityIndicator size="small" style={{ marginLeft: 8 }} />}
            </TouchableOpacity>
            
            <TouchableOpacity
              style={styles.optionButton}
              onPress={handleCamera}
              disabled={uploading}
            >
              <MaterialIcons name="camera-alt" size={24} color={colors.primary} />
              <Text variant="bodyLarge" style={[styles.optionText, { color: colors.onSurface }]}>
                拍照
              </Text>
            </TouchableOpacity>
            
            <TouchableOpacity
              style={[styles.cancelButton, { borderTopColor: colors.outlineVariant }]}
              onPress={hidePickerOptions}
              disabled={uploading}
            >
              <Text variant="bodyLarge" style={{ color: colors.error }}>
                取消
              </Text>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
  },
  attachmentList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  attachmentItem: {
    position: 'relative',
    width: 72,
    height: 72,
    borderRadius: 8,
    overflow: 'hidden',
  },
  attachmentImage: {
    width: '100%',
    height: '100%',
    resizeMode: 'cover',
  },
  uploadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  errorOverlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(255, 0, 0, 0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeButton: {
    position: 'absolute',
    top: 4,
    right: 4,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addButton: {
    width: 72,
    height: 72,
    borderRadius: 8,
    borderWidth: 1,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
  },
  toolbar: {
    flexDirection: 'row',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 16,
  },
  toolbarButton: {
    padding: 8,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    paddingBottom: 32,
  },
  modalTitle: {
    textAlign: 'center',
    marginBottom: 16,
    fontWeight: '600',
  },
  optionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 16,
    gap: 16,
  },
  optionText: {
    fontSize: 16,
    flex: 1,
  },
  cancelButton: {
    alignItems: 'center',
    paddingTop: 16,
    marginTop: 8,
    borderTopWidth: 1,
  },
});
