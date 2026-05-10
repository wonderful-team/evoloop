// 主题导出

import { useTheme as usePaperTheme } from 'react-native-paper';

// 扩展的颜色配置
export interface ExtendedColors {
  background: string;
  surface: string;
  surfaceVariant: string;
  primary: string;
  primaryContainer: string;
  onPrimary: string;
  onPrimaryContainer: string;
  onSurface: string;
  onSurfaceVariant: string;
  secondary: string;
  secondaryContainer: string;
  error: string;
  errorContainer: string;
  onError: string;
  onErrorContainer: string;
  warning: string;
  warningContainer: string;
  onWarning: string;
  onWarningContainer: string;
  success: string;
  successContainer: string;
  onSuccess: string;
  onSuccessContainer: string;
  info: string;
  infoContainer: string;
  onInfo: string;
  onInfoContainer: string;
  text: {
    primary: string;
    secondary: string;
    tertiary: string;
    disabled: string;
  };
  outline: string;
  outlineVariant: string;
  status: {
    error: string;
    warning: string;
    success: string;
    info: string;
  };
  elevation: {
    level0: string;
    level1: string;
    level2: string;
    level3: string;
    level4: string;
    level5: string;
  };
}


// 扩展主题 Hook
export function useTheme() {
  const theme = usePaperTheme();

  const colors: ExtendedColors = {
    background: theme.colors.background,
    surface: theme.colors.surface,
    surfaceVariant: theme.colors.surfaceVariant || theme.colors.surface,
    primary: theme.colors.primary,
    primaryContainer: theme.colors.primaryContainer,
    onPrimary: theme.colors.onPrimary,
    onPrimaryContainer: theme.colors.onPrimaryContainer,
    onSurface: theme.colors.onSurface,
    onSurfaceVariant: theme.colors.onSurfaceVariant || theme.colors.onSurface,
    secondary: theme.colors.secondary,
    secondaryContainer: theme.colors.secondaryContainer,
    error: theme.colors.error,
    errorContainer: theme.colors.errorContainer,
    onError: theme.colors.onError,
    onErrorContainer: theme.colors.onErrorContainer || theme.colors.error,
    warning: '#FFAB00',
    warningContainer: '#FFF3E0',
    onWarning: '#FFFFFF',
    onWarningContainer: '#663C00',
    success: '#00C853',
    successContainer: '#E8F5E9',
    onSuccess: '#FFFFFF',
    onSuccessContainer: '#1B5E20',
    info: '#109C8F',
    infoContainer: '#E3F2FD',
    onInfo: '#FFFFFF',
    onInfoContainer: '#0D47A1',

    text: {
      primary: theme.colors.onSurface,
      secondary: theme.colors.onSurfaceVariant || theme.colors.onSurface,
      tertiary: theme.dark ? '#888888' : '#A0A0A0',
      disabled: theme.colors.onSurfaceDisabled || theme.colors.onSurfaceVariant,
    },
    outline: theme.colors.outline,
    outlineVariant: theme.colors.outlineVariant || theme.colors.outline,
    status: {
      error: '#FF3D00',
      warning: '#FFAB00',
      success: '#00C853',
      info: '#109C8F',
    },
    elevation: theme.colors.elevation || {
      level0: theme.colors.surface,
      level1: theme.colors.surface,
      level2: theme.colors.surface,
      level3: theme.colors.surface,
      level4: theme.colors.surface,
      level5: theme.colors.surface,
    },
  };


  return {
    colors,
    theme,
  };
}

export * from '@/constants/theme';
