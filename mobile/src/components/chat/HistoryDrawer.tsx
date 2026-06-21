// 历史会话抽屉 - 从 ChatScreen 中提取的 UI 组件

import React, { useRef, useEffect } from 'react';
import {
  View,
  StyleSheet,
  Modal,
  TouchableOpacity,
  Animated,
} from 'react-native';
import { ThreadList } from './ThreadList';
import { Portal } from 'react-native-paper';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

interface HistoryDrawerProps {
  visible: boolean;
  onClose: () => void;
  projectId?: number;
  deviceKey?: string;
  onSelectThread: (threadId: string) => void;
  onNewThread: () => void;
}

export function HistoryDrawer({
  visible,
  onClose,
  projectId,
  deviceKey,
  onSelectThread,
  onNewThread,
}: HistoryDrawerProps) {
  const slideAnim = useRef(new Animated.Value(-320)).current;

  useEffect(() => {
    if (visible) {
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 250,
        useNativeDriver: true,
      }).start();
    } else {
      Animated.timing(slideAnim, {
        toValue: -320,
        duration: 200,
        useNativeDriver: true,
      }).start();
    }
  }, [visible]);

  return (
    <Modal
      visible={visible}
      transparent={true}
      animationType="none"
      onRequestClose={onClose}
    >
      <GestureHandlerRootView style={{ flex: 1 }}>
        <Portal.Host>
          <View style={styles.container}>
            <Animated.View
              style={[
                styles.drawer,
                { transform: [{ translateX: slideAnim }] },
              ]}
            >
              <ThreadList
                projectId={projectId}
                deviceKey={deviceKey}
                onSelectThread={onSelectThread}
                onNewThread={onNewThread}
              />
            </Animated.View>
            <TouchableOpacity
              style={styles.overlay}
              activeOpacity={1}
              onPress={onClose}
            />
          </View>
        </Portal.Host>
      </GestureHandlerRootView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    flexDirection: 'row',
  },
  drawer: {
    width: 320,
    height: '100%',
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
});
