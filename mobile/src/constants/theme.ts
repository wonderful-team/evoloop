import { MD3LightTheme, MD3DarkTheme } from 'react-native-paper';

// 品牌色 - EvoLoop Teal 主题（与旧版移动端/桌面端一致）
export const brandColors = {
  primary: '#109C8F',      // 主色 teal（匹配旧版 oklch(0.5982 0.10687 182.4689)）
  secondary: '#0D9488',    // 深 teal
  accent: '#14B8A6',       // 亮 teal
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
    primaryContainer: '#E6F4F3',      // 极浅 teal 灰
    onPrimary: '#FFFFFF',
    onPrimaryContainer: '#0A3D38',    // 深 teal 文字
    secondary: '#F5F5F5',             // 中性浅灰
    secondaryContainer: '#F5F5F5',
    onSecondary: '#1A1A1A',
    onSecondaryContainer: '#1A1A1A',
    error: brandColors.error,
    errorContainer: '#FEE2E2',
    onError: '#FFFFFF',
    background: '#FFFFFF',
    surface: '#FFFFFF',
    surfaceVariant: '#F5F5F5',        // 中性浅灰
    onSurface: '#242424',              // 匹配旧版 foreground oklch(0.145)
    onSurfaceVariant: '#757575',       // 匹配旧版 muted-foreground oklch(0.556)
    outline: '#E5E5E5',
    outlineVariant: '#EBEBEB',
  },
};

// 深色主题
export const darkTheme = {
  ...MD3DarkTheme,
  colors: {
    ...MD3DarkTheme.colors,
    primary: '#14B8A6',               // 亮 teal（暗色模式下更醒目）
    primaryContainer: '#134E4A',      // 深 teal 容器
    onPrimary: '#FFFFFF',
    onPrimaryContainer: '#E6F4F3',
    secondary: '#2A2A2A',             // 暗灰
    secondaryContainer: '#333333',
    onSecondary: '#FFFFFF',
    onSecondaryContainer: '#F5F5F5',
    error: brandColors.error,
    errorContainer: '#7F1D1D',
    onError: '#FFFFFF',
    background: '#1A1A1A',
    surface: '#242424',
    surfaceVariant: '#2A2A2A',        // 中性暗灰
    onSurface: '#FAFAFA',              // 匹配旧版 dark foreground oklch(0.985)
    onSurfaceVariant: '#A8A8A8',       // 匹配旧版 dark muted-foreground oklch(0.708)
    outline: '#404040',
    outlineVariant: '#333333',
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
