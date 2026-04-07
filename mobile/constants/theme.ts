import { MD3LightTheme, MD3DarkTheme } from 'react-native-paper';

// 品牌色
export const brandColors = {
  primary: '#0066FF',
  secondary: '#00C853',
  warning: '#FFAB00',
  error: '#FF3D00',
  wechat: '#07C160',
};

// 浅色主题
export const lightTheme = {
  ...MD3LightTheme,
  colors: {
    ...MD3LightTheme.colors,
    primary: brandColors.primary,
    secondary: brandColors.secondary,
    error: brandColors.error,
    background: '#FFFFFF',
    surface: '#FFFFFF',
    onSurface: '#1A1A1A',
    onSurfaceVariant: '#666666',
  },
};

// 深色主题
export const darkTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: brandColors.primary,
    secondary: brandColors.secondary,
    error: brandColors.error,
    background: '#121212',
    surface: '#1E1E1E',
    onSurface: '#FFFFFF',
    onSurfaceVariant: '#A0A0A0',
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
