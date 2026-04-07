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
import { MaterialIcons } from '@expo/vector-icons';

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
  const { colors } = useTheme();
  const [revertFiles, setRevertFiles] = useState(true);

  const title = mode === 'rewind' ? '确认撤回' : '确认重试';
  const description = mode === 'rewind'
    ? '将删除此消息及其后的所有内容。此操作不可撤销。'
    : '将删除后续内容并重新尝试执行。';

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
                    同时恢复 Agent 修改过的文件内容
                  </Text>
                  <Text style={{ color: colors.outline, fontSize: 12, marginTop: 2 }}>
                    恢复到修改前的状态
                  </Text>
                </View>
              </View>
            </>
          )}
        </Dialog.Content>
        
        <Dialog.Actions style={styles.actions}>
          <Button
            onPress={onDismiss}
            textColor={colors.outline}
          >
            取消
          </Button>
          <Button
            mode="contained"
            onPress={handleConfirm}
            buttonColor={mode === 'rewind' ? colors.error : colors.primary}
            textColor={colors.onError}
          >
            {mode === 'rewind' ? '确认撤回' : '确认重试'}
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
