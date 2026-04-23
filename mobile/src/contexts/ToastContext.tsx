// 全局 Toast 上下文
// 提供全局错误提示功能，API 错误自动显示

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react';
import { Toast, ToastType } from '@/components/feedback';

interface ToastContextValue {
  show: (message: string, type?: ToastType) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  warning: (message: string) => void;
  info: (message: string) => void;
  hide: () => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

interface ToastState {
  visible: boolean;
  message: string;
  type: ToastType;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ToastState>({
    visible: false,
    message: '',
    type: 'info',
  });

  const show = useCallback((message: string, type: ToastType = 'info') => {
    setState({ visible: true, message, type });
  }, []);

  const hide = useCallback(() => {
    setState((prev) => ({ ...prev, visible: false }));
  }, []);

  const success = useCallback((message: string) => show(message, 'success'), [show]);
  const error = useCallback((message: string) => show(message, 'error'), [show]);
  const warning = useCallback((message: string) => show(message, 'warning'), [show]);
  const info = useCallback((message: string) => show(message, 'info'), [show]);

  return (
    <ToastContext.Provider value={{ show, success, error, warning, info, hide }}>
      {children}
      <Toast
        visible={state.visible}
        message={state.message}
        type={state.type}
        onDismiss={hide}
      />
    </ToastContext.Provider>
  );
}

export function useGlobalToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useGlobalToast must be used within ToastProvider');
  }
  return context;
}

// 全局 toast 实例（用于非组件场景，如 API 错误）
let globalToast: ToastContextValue | null = null;

export function setGlobalToast(toast: ToastContextValue) {
  globalToast = toast;
}

export function showGlobalToast(message: string, type: ToastType = 'error') {
  globalToast?.show(message, type);
}

export function showGlobalError(message: string) {
  globalToast?.error(message);
}

export function showGlobalSuccess(message: string) {
  globalToast?.success(message);
}
