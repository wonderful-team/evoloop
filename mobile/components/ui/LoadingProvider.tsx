// 全局加载状态提供者

import React, { createContext, useContext, useState, useCallback } from 'react';
import { View, StyleSheet, ActivityIndicator } from 'react-native';
import { Portal, Modal } from 'react-native-paper';

interface LoadingContextType {
  showLoading: (message?: string) => void;
  hideLoading: () => void;
  isLoading: boolean;
}

const LoadingContext = createContext<LoadingContextType>({
  showLoading: () => {},
  hideLoading: () => {},
  isLoading: false,
});

export const useLoading = () => useContext(LoadingContext);

interface LoadingProviderProps {
  children: React.ReactNode;
}

export function LoadingProvider({ children }: LoadingProviderProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string>('加载中...');
  
  const showLoading = useCallback((msg?: string) => {
    if (msg) setMessage(msg);
    setIsLoading(true);
  }, []);
  
  const hideLoading = useCallback(() => {
    setIsLoading(false);
    setMessage('加载中...');
  }, []);
  
  return (
    <LoadingContext.Provider value={{ showLoading, hideLoading, isLoading }}>
      {children}
      <Portal>
        <Modal
          visible={isLoading}
          dismissable={false}
          contentContainerStyle={styles.modal}
        >
          <View style={styles.container}>
            <ActivityIndicator size="large" color="#0066FF" />
          </View>
        </Modal>
      </Portal>
    </LoadingContext.Provider>
  );
}

const styles = StyleSheet.create({
  modal: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  container: {
    backgroundColor: 'rgba(0, 0, 0, 0.7)',
    padding: 24,
    borderRadius: 12,
    alignItems: 'center',
  },
});
