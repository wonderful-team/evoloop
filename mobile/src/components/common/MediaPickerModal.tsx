// 通用媒体选择底部面板 - 支持拍照、录视频、相册、文件选择

import React, { useCallback } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Modal,
  Alert,
  Platform,
  PermissionsAndroid,
} from 'react-native';
import { Text } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';
import ImagePicker, { ImageOrVideo } from 'react-native-image-crop-picker';
import { requestCameraPermission as reqCameraPermission, requestPhotoLibraryPermission as reqPhotoLibraryPermission } from '@/utils/permissions';

export type MediaOption = 'camera' | 'video' | 'album' | 'file';

export interface MediaPickerModalProps {
  visible: boolean;
  onClose: () => void;
  /** 显示的选项，默认 ['camera', 'video', 'album', 'file'] */
  options?: MediaOption[];
  /** 最大可选文件数（相册/文件多选时） */
  maxFiles?: number;
  /** 是否启用裁剪 */
  cropping?: boolean;
  /** 是否显示圆形裁剪遮罩 */
  cropperCircleOverlay?: boolean;
  /** 是否包含 base64 数据 */
  includeBase64?: boolean;
  /** 裁剪目标宽度 */
  width?: number;
  /** 裁剪目标高度 */
  height?: number;
  /** 压缩后最大宽度 */
  compressImageMaxWidth?: number;
  /** 压缩后最大高度 */
  compressImageMaxHeight?: number;
  /** 图片压缩质量 0-1 */
  compressImageQuality?: number;
  /** 图片/视频选择回调 */
  onSelectImage?: (images: ImageOrVideo[]) => void;
  /** 文件选择回调 */
  onSelectFile?: (files: any[]) => void;
}

interface OptionConfig {
  key: MediaOption;
  icon: string;
  label: string;
}

const OPTION_CONFIGS: OptionConfig[] = [
  { key: 'camera', icon: 'photo-camera', label: 'camera' },
  { key: 'video', icon: 'videocam', label: 'video' },
  { key: 'album', icon: 'image', label: 'album' },
  { key: 'file', icon: 'insert-drive-file', label: 'file' },
];

export function MediaPickerModal({
  visible,
  onClose,
  options = ['camera', 'video', 'album', 'file'],
  maxFiles = 5,
  cropping = false,
  cropperCircleOverlay = false,
  includeBase64 = false,
  width,
  height,
  compressImageMaxWidth,
  compressImageMaxHeight,
  compressImageQuality = 0.8,
  onSelectImage,
  onSelectFile,
}: MediaPickerModalProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();

  const requestCameraPermission = useCallback(async () => {
    return reqCameraPermission();
  }, []);

  const requestMediaLibraryPermission = useCallback(async () => {
    return reqPhotoLibraryPermission();
  }, []);

  const isUserCancelled = (error: any): boolean => {
    if (!error) return false;
    const msg = typeof error === 'string' ? error : error.message || '';
    const code = error.code || '';
    return (
      msg.toLowerCase().includes('cancel') ||
      code === 'E_PICKER_CANCELLED' ||
      code === 'E_USER_CANCELLED'
    );
  };

  const handleCamera = useCallback(async () => {
    onClose();
    const hasPermission = await requestCameraPermission();
    if (!hasPermission) {
      Alert.alert(t('mediaPicker.permissionDenied'), t('mediaPicker.cameraPermission'));
      return;
    }
    try {
      const result = await ImagePicker.openCamera({
        mediaType: 'photo',
        cropping,
        cropperCircleOverlay,
        includeBase64,
        width,
        height,
        compressImageMaxWidth,
        compressImageMaxHeight,
        compressImageQuality,
      });
      onSelectImage?.([result]);
    } catch (error: any) {
      if (isUserCancelled(error)) return;
      Alert.alert(t('common.error.title'), t('mediaPicker.cameraError'));
    }
  }, [
    onClose, requestCameraPermission, onSelectImage,
    cropping, cropperCircleOverlay, includeBase64,
    width, height, compressImageMaxWidth, compressImageMaxHeight, compressImageQuality,
  ]);

  const handleVideo = useCallback(async () => {
    onClose();
    const hasPermission = await requestCameraPermission();
    if (!hasPermission) {
      Alert.alert(t('mediaPicker.permissionDenied'), t('mediaPicker.videoPermission'));
      return;
    }
    try {
      const result = await ImagePicker.openCamera({
        mediaType: 'video',
      });
      onSelectImage?.([result]);
    } catch (error: any) {
      if (isUserCancelled(error)) return;
      Alert.alert(t('common.error.title'), t('mediaPicker.videoError'));
    }
  }, [onClose, requestCameraPermission, onSelectImage]);

  const handleAlbum = useCallback(async () => {
    onClose();
    const hasPermission = await requestMediaLibraryPermission();
    if (!hasPermission) {
      Alert.alert(t('mediaPicker.permissionDenied'), t('mediaPicker.albumPermission'));
      return;
    }
    try {
      const result = await ImagePicker.openPicker({
        mediaType: options.includes('video') ? 'any' : 'photo',
        multiple: maxFiles > 1,
        maxFiles,
        cropping,
        cropperCircleOverlay,
        includeBase64,
        width,
        height,
        compressImageMaxWidth,
        compressImageMaxHeight,
        compressImageQuality,
      });
      const items = Array.isArray(result) ? result : [result];
      onSelectImage?.(items);
    } catch (error: any) {
      if (isUserCancelled(error)) return;
      Alert.alert(t('common.error.title'), t('mediaPicker.albumError'));
    }
  }, [
    onClose, requestMediaLibraryPermission, onSelectImage, maxFiles,
    cropping, cropperCircleOverlay, includeBase64,
    width, height, compressImageMaxWidth, compressImageMaxHeight, compressImageQuality,
  ]);

  const handleFile = useCallback(async () => {
    onClose();
    try {
      const DocumentPicker = require('react-native-document-picker').default;
      const result = await DocumentPicker.pick({
        type: [DocumentPicker.types.allFiles],
        allowMultiSelection: maxFiles > 1,
      });
      const files = Array.isArray(result) ? result : [result];
      onSelectFile?.(files.slice(0, maxFiles));
    } catch (error: any) {
      if (isUserCancelled(error)) return;
      if (error.message?.includes('Native module')) {
        Alert.alert(
          t('mediaPicker.fileUploadTitle'),
          t('mediaPicker.fileUploadMessage')
        );
        return;
      }
      Alert.alert(t('common.error.title'), error.message || t('mediaPicker.fileError'));
    }
  }, [onClose, onSelectFile, maxFiles]);

  const handlers: Record<MediaOption, () => void> = {
    camera: handleCamera,
    video: handleVideo,
    album: handleAlbum,
    file: handleFile,
  };

  const visibleOptions = OPTION_CONFIGS.filter((cfg) => options.includes(cfg.key));

  if (visibleOptions.length === 0) return null;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <TouchableOpacity
        style={styles.overlay}
        activeOpacity={1}
        onPress={onClose}
      >
        <View style={[styles.content, { backgroundColor: colors.surface }]}>
          <View style={styles.grid}>
            {visibleOptions.map((cfg) => (
              <TouchableOpacity
                key={cfg.key}
                style={styles.item}
                onPress={handlers[cfg.key]}
              >
                <View
                  style={[
                    styles.iconContainer,
                    { backgroundColor: colors.primaryContainer },
                  ]}
                >
                  <MaterialIcons
                    name={cfg.icon as any}
                    size={28}
                    color={colors.primary}
                  />
                </View>
                <Text
                  variant="bodySmall"
                  style={{ color: colors.onSurface, marginTop: 8 }}
                >
                  {t(`mediaPicker.${cfg.label}`)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  content: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingTop: 24,
    paddingBottom: 32,
    paddingHorizontal: 20,
  },
  grid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  item: {
    alignItems: 'center',
    width: 72,
  },
  iconContainer: {
    width: 56,
    height: 56,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
