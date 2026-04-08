import { MD3LightTheme, MD3DarkTheme } from 'react-native-paper';

// 品牌色 - EvoLoop 绿色主题
export const brandColors = {
  primary: '#22C55E',      // 主绿色
  secondary: '#16A34A',    // 深绿色
  accent: '#4ADE80',       // 亮绿色
  warning: '#F59E0B',
  error: '#EF4444',
  wechat: '#07C160',
};

// 浅色主题
export const lightTheme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: brandColors.primary,
    primaryContainer: '#DCFCE7',      // 浅绿色容器
    onPrimary: '#FFFFFF',
    onPrimaryContainer: '#14532D',    // 深绿色文字
    secondary: brandColors.secondary,
    secondaryContainer: '#DCFCE7',
    onSecondary: '#FFFFFF',
    onSecondaryContainer: '#14532D',
    error: brandColors.error,
    errorContainer: '#FEE2E2',
    onError: '#FFFFFF',
    background: '#FFFFFF',
    surface: '#FFFFFF',
    surfaceVariant: '#F0FDF4',        // 极浅绿色背景
    onSurface: '#1A1A1A',
    onSurfaceVariant: '#666666',
    outline: '#BBF7D0',
    outlineVariant: '#DCFCE7',
  },
};

// 深色主题
export const darkTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: brandColors.primary,
    primaryContainer: '#14532D',      // 深绿色容器
    onPrimary: '#FFFFFF',
    onPrimaryContainer: '#DCFCE7',    // 浅绿色文字
    secondary: brandColors.secondary,
    secondaryContainer: '#14532D',
    onSecondary: '#FFFFFF',
    onSecondaryContainer: '#DCFCE7',
    error: brandColors.error,
    errorContainer: '#7F1D1D',
    onError: '#FFFFFF',
    background: '#121212',
    surface: '#1E1E1E',
    surfaceVariant: '#166534',        // 深绿色表面
    onSurface: '#FFFFFF',
    onSurfaceVariant: '#A0A0A0',
    outline: '#22C55E',
    outlineVariant: '#14532D',
  },
};

// 间距规范
export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

// 字体大小
export const typography = {
  xs: 12,
  sm: 14,
  base: 16,
  lg: 18,
  xl: 20,
  '2xl': 24,
  '3xl': 30,
};

// 圆角
export const borderRadius = {
  sm: 4,
  base: 8,
  lg: 12,
  xl: 16,
  full: 9999,
};
