// 基础按钮组件

import React from 'react';
import { Button as PaperButton, ButtonProps } from 'react-native-paper';

interface CustomButtonProps extends ButtonProps {
  loading?: boolean;
}

export function Button({ children, loading, disabled, ...props }: CustomButtonProps) {
  return (
    <PaperButton
      {...props}
      loading={loading}
      disabled={disabled || loading}
    >
      {children}
    </PaperButton>
  );
}
