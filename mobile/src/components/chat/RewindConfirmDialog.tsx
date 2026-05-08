// Rewind/Retry 确认对话框

import React, { useState } from 'react';
import { View, StyleSheet } from 'react-native';
import {
  Dialog,
  Portal,
  Text,
  Button,
  Checkbox,
  Divider,
} from 'react-native-paper';
import { useTheme } from '@/theme';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTranslation } from 'react-i18next';

interface RewindConfirmDialogProps {
  visible: boolean;
  onDismiss: () => void;
  onConfirm: (revertFiles: boolean) => void;
  mode?: 'rewind' | 'retry';
  hasFileOperations?: boolean;
}

export function RewindConfirmDialog({
  visible,
  onDismiss,
  onConfirm,
  mode = 'rewind',
  hasFileOperations = false,
}: RewindConfirmDialogProps) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const [revertFiles, setRevertFiles] = useState(true);

  const title = mode === 'rewind' ? t('chat.rewindConfirm.rewindTitle') : t('chat.rewindConfirm.retryTitle');
  const description = mode === 'rewind'
    ? t('chat.rewindConfirm.rewindDesc')
    : t('chat.rewindConfirm.retryDesc');

  const handleConfirm = () => {
    onConfirm(revertFiles);
    setRevertFiles(true); // 重置状态
  };

  return (
    <Portal>
      <Dialog visible={visible} onDismiss={onDismiss} style={styles.dialog}>
        <Dialog.Title style={{ color: colors.onSurface }}>
          <View style={styles.titleContainer}>
            <MaterialIcons
              name={mode === 'rewind' ? 'undo' : 'refresh'}
              size={24}
              color={colors.primary}
              style={{ marginRight: 8 }}
            />
            <Text style={{ color: colors.onSurface, fontWeight: '600' }}>
              {title}
            </Text>
          </View>
        </Dialog.Title>
        
        <Dialog.Content>
          <Text style={[styles.description, { color: colors.onSurfaceVariant }]}>
            {description}
          </Text>

          {hasFileOperations && (
            <>
              <Divider style={[styles.divider, { backgroundColor: colors.outline + '30' }]} />
              
              <View style={styles.checkboxContainer}>
                <Checkbox.Android
                  status={revertFiles ? 'checked' : 'unchecked'}
                  onPress={() => setRevertFiles(!revertFiles)}
                  color={colors.primary}
                />
                <View style={styles.checkboxLabel}>
                  <Text style={{ color: colors.onSurface, fontWeight: '500' }}>
                    {t('chat.rewindConfirm.revertFiles')}
                  </Text>
                  <Text style={{ color: colors.onSurfaceVariant, fontSize: 12, marginTop: 2 }}>
                    {t('chat.rewindConfirm.revertToPrevious')}
                  </Text>
                </View>
              </View>
            </>
          )}
        </Dialog.Content>
        
        <Dialog.Actions style={styles.actions}>
          <Button
            onPress={onDismiss}
            textColor={colors.onSurfaceVariant}
          >
            {t('chat.rewindConfirm.cancel')}
          </Button>
          <Button
            mode="contained"
            onPress={handleConfirm}
            buttonColor={mode === 'rewind' ? colors.error : colors.primary}
            textColor={colors.onError}
          >
            {mode === 'rewind' ? t('chat.rewindConfirm.confirmRewind') : t('chat.rewindConfirm.confirmRetry')}
          </Button>
        </Dialog.Actions>
      </Dialog>
    </Portal>
  );
}

const styles = StyleSheet.create({
  dialog: {
    borderRadius: 16,
    marginHorizontal: 24,
  },
  titleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  description: {
    fontSize: 14,
    lineHeight: 20,
  },
  divider: {
    marginVertical: 16,
  },
  checkboxContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  checkboxLabel: {
    flex: 1,
    marginLeft: 8,
  },
  actions: {
    paddingHorizontal: 16,
    paddingBottom: 16,
    justifyContent: 'flex-end',
  },
});
