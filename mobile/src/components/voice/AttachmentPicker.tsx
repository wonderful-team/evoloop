// 附件选择组件 - 支持图片选择和相机拍照

import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Image,
  Modal,
  Alert,
  ActivityIndicator,
  PermissionsAndroid,
  Platform,
} from 'react-native';
import { Text } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import ImagePicker from 'react-native-image-crop-picker';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';
import { uploadChatImage, ChatAttachment } from '@/services/api/upload';

export { type ChatAttachment } from '@/services/api/upload';

export interface Attachment {
  id: string;
  type: 'image' | 'video';
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
  const { t } = useTranslation();
  const [showOptions, setShowOptions] = useState(false);
  const [uploading, setUploading] = useState(false);

  // 自动上传未上传的附件
  useEffect(() => {
    const pendingAttachments = attachments.filter(att => !att.uploaded && !att.uploading);
    if (pendingAttachments.length === 0 || uploading) return;

    let cancelled = false;
    const uploadPending = async () => {
      setUploading(true);
      const uploadedAttachments: ChatAttachment[] = [];

      for (const attachment of pendingAttachments) {
        if (cancelled) break;
        try {
          const uploaded = await uploadSingleImage(attachment);
          if (uploaded.url) {
            uploadedAttachments.push({
              type: uploaded.type || 'image',
              url: uploaded.url,
              name: uploaded.name || '',
              ext: uploaded.name?.split('.').pop() || (uploaded.type === 'video' ? 'mp4' : 'jpg'),
            });
          }
        } catch (error: any) {
          console.error('自动上传失败:', error);
        }
      }

      if (!cancelled) {
        setUploading(false);
        if (uploadedAttachments.length > 0) {
          onUploadComplete?.(uploadedAttachments);
        }
      }
    };

    uploadPending();
    return () => { cancelled = true; };
  }, [attachments, uploading, onUploadComplete, uploadSingleImage]);

  // 请求相机权限 (Android)
  const requestCameraPermission = useCallback(async () => {
    if (Platform.OS === 'android') {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.CAMERA,
        {
          title: t('common.cameraPermissionTitle'),
          message: t('common.cameraPermissionMessage'),
          buttonNeutral: t('common.later'),
          buttonNegative: t('common.cancel'),
          buttonPositive: t('common.confirm'),
        }
      );
      return granted === PermissionsAndroid.RESULTS.GRANTED;
    }
    return true;
  }, []);

  // 请求相册权限 (Android)
  const requestMediaLibraryPermission = useCallback(async () => {
    if (Platform.OS === 'android') {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.READ_EXTERNAL_STORAGE,
        {
          title: t('common.albumPermissionTitle'),
          message: t('common.albumPermissionMessage'),
          buttonNeutral: t('common.later'),
          buttonNegative: t('common.cancel'),
          buttonPositive: t('common.confirm'),
        }
      );
      return granted === PermissionsAndroid.RESULTS.GRANTED;
    }
    return true;
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
      Alert.alert(t('common.tip'), t('common.maxAttachments', { count: maxAttachments }));
      return;
    }

    const hasPermission = await requestMediaLibraryPermission();
    if (!hasPermission) {
      Alert.alert(t('common.permissionDenied'), t('common.albumPermissionRequired'));
      return;
    }

    try {
      const result = await ImagePicker.openPicker({
        mediaType: 'any',
        multiple: true,
        maxFiles: maxAttachments - attachments.length,
        compressImageQuality: 0.8,
      });

      // 处理单张或多张媒体文件
      const assets = Array.isArray(result) ? result : [result];

      const newAttachments: Attachment[] = assets.map((asset, index) => {
        const isVideo = asset.mime?.startsWith('video/') || asset.path?.match(/\.(mp4|mov|avi|mkv|wmv)$/i);
        return {
          id: `${isVideo ? 'vid' : 'img'}_${Date.now()}_${index}`,
          type: isVideo ? 'video' : 'image',
          uri: asset.path,
          name: asset.filename || `${isVideo ? 'video' : 'image'}_${Date.now()}_${index}.${isVideo ? 'mp4' : 'jpg'}`,
          mimeType: asset.mime || (isVideo ? 'video/mp4' : 'image/jpeg'),
          size: asset.size,
          uploading: false,
          uploaded: false,
        };
      });

      onAttachmentsChange([...attachments, ...newAttachments]);
      // 上传由 useEffect 自动处理
    } catch (error: any) {
      // 用户取消选择时不报错
      if (error.message?.includes('cancel') || error.message?.includes('Cancel')) {
        return;
      }
      console.error('选择媒体失败:', error);
      Alert.alert(t('common.error.title'), t('common.mediaPickError'));
    }
  }, [attachments, maxAttachments, onAttachmentsChange, requestMediaLibraryPermission]);

  // 处理相机拍照
  const handleCamera = useCallback(async () => {
    setShowOptions(false);

    if (attachments.length >= maxAttachments) {
      Alert.alert(t('common.tip'), t('common.maxAttachments', { count: maxAttachments }));
      return;
    }

    const hasPermission = await requestCameraPermission();
    if (!hasPermission) {
      Alert.alert(t('common.permissionDenied'), t('common.cameraPermissionRequired'));
      return;
    }

    try {
      const result = await ImagePicker.openCamera({
        mediaType: 'photo',
        compressImageQuality: 0.8,
      });

      const newAttachment: Attachment = {
        id: `camera_${Date.now()}`,
        type: 'image',
        uri: result.path,
        name: result.filename || `camera_${Date.now()}.jpg`,
        mimeType: result.mime || 'image/jpeg',
        size: result.size,
        uploading: false,
        uploaded: false,
      };

      onAttachmentsChange([...attachments, newAttachment]);
      // 上传由 useEffect 自动处理
    } catch (error: any) {
      // 用户取消拍照时不报错
      if (error.message?.includes('cancel') || error.message?.includes('Cancel')) {
        return;
      }
      console.error('拍照失败:', error);
      Alert.alert(t('common.error.title'), t('common.cameraError'));
    }
  }, [attachments, maxAttachments, onAttachmentsChange, requestCameraPermission]);

  // 处理视频录制
  const handleVideoRecord = useCallback(async () => {
    setShowOptions(false);

    if (attachments.length >= maxAttachments) {
      Alert.alert(t('common.tip'), t('common.maxAttachments', { count: maxAttachments }));
      return;
    }

    const hasPermission = await requestCameraPermission();
    if (!hasPermission) {
      Alert.alert(t('common.permissionDenied'), t('common.videoPermissionRequired'));
      return;
    }

    try {
      const result = await ImagePicker.openCamera({
        mediaType: 'video',
      });

      const newAttachment: Attachment = {
        id: `vid_${Date.now()}`,
        type: 'video',
        uri: result.path,
        name: result.filename || `video_${Date.now()}.mp4`,
        mimeType: result.mime || 'video/mp4',
        size: result.size,
        uploading: false,
        uploaded: false,
      };

      onAttachmentsChange([...attachments, newAttachment]);
      // 上传由 useEffect 自动处理
    } catch (error: any) {
      // 用户取消录制时不报错
      if (error.message?.includes('cancel') || error.message?.includes('Cancel')) {
        return;
      }
      console.error('录制视频失败:', error);
      Alert.alert(t('common.error.title'), t('common.videoError'));
    }
  }, [attachments, maxAttachments, onAttachmentsChange, requestCameraPermission]);

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
              {att.type === 'video' ? (
                <View style={[styles.attachmentImage, { backgroundColor: colors.surfaceVariant, alignItems: 'center', justifyContent: 'center' }]}>
                  <MaterialIcons name="videocam" size={28} color={colors.primary} />
                </View>
              ) : (
                <Image source={{ uri: att.uri }} style={styles.attachmentImage} />
              )}

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
              <MaterialIcons name="add" size={24} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* 附件选择按钮已移除 */}

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
              {t('mediaPicker.selectMedia')}
            </Text>
            
            <TouchableOpacity
              style={styles.optionButton}
              onPress={handleImagePick}
              disabled={uploading}
            >
              <MaterialIcons name="image" size={24} color={colors.primary} />
              <Text variant="bodyLarge" style={[styles.optionText, { color: colors.onSurface }]}>
                {t('mediaPicker.fromAlbum')}
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
                {t('mediaPicker.takePhoto')}
              </Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={styles.optionButton}
              onPress={handleVideoRecord}
              disabled={uploading}
            >
              <MaterialIcons name="videocam" size={24} color={colors.primary} />
              <Text variant="bodyLarge" style={[styles.optionText, { color: colors.onSurface }]}>
                {t('mediaPicker.recordVideo')}
              </Text>
            </TouchableOpacity>
            
            <TouchableOpacity
              style={[styles.cancelButton, { borderTopColor: colors.outlineVariant }]}
              onPress={hidePickerOptions}
              disabled={uploading}
            >
              <Text variant="bodyLarge" style={{ color: colors.error }}>
                {t('common.cancel')}
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
