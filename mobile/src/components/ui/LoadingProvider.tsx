// 全局加载状态提供者

import React, { createContext, useContext, useState, useCallback } from 'react';
import { View, StyleSheet, ActivityIndicator } from 'react-native';
import { Portal, Modal, useTheme } from 'react-native-paper';
import { useTranslation } from 'react-i18next';

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
  const { colors } = useTheme();
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string>(t('common.loading'));

  const showLoading = useCallback((msg?: string) => {
    if (msg) setMessage(msg);
    setIsLoading(true);
  }, []);

  const hideLoading = useCallback(() => {
    setIsLoading(false);
    setMessage(t('common.loading'));
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
            <ActivityIndicator size="large" color={colors.primary} />
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
