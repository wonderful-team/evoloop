// Mermaid 图表组件 - 使用 WebView 渲染

import React, { useState, useCallback, memo } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Modal,
  Dimensions,
} from 'react-native';
import { Text, IconButton, ActivityIndicator } from 'react-native-paper';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';
import { WebView } from 'react-native-webview';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

interface MermaidChartProps {
  chart: string;
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

// 生成 Mermaid 渲染 HTML
const generateMermaidHtml = (chart: string) => `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>
    mermaid.initialize({
      startOnLoad: true,
      theme: 'default',
      securityLevel: 'strict',
    });
  </script>
  <style>
    body { 
      margin: 0; 
      padding: 16px;
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: 100vh;
      background: transparent;
    }
    .mermaid { 
      max-width: 100%;
    }
  </style>
</head>
<body>
  <div class="mermaid">
${chart}
  </div>
</body>
</html>
`;

export const MermaidChart = memo(function MermaidChart({ chart }: MermaidChartProps) {
  const { colors, isDark } = useTheme();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [height, setHeight] = useState(200);

  const handleLoadEnd = useCallback(() => {
    setLoading(false);
  }, []);

  const handleError = useCallback(() => {
    setError(true);
    setLoading(false);
  }, []);

  const handleMessage = useCallback((event: { nativeEvent: { data: string } }) => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.type === 'height' && data.value) {
        setHeight(data.value);
      }
    } catch {
      // 忽略解析错误
    }
  }, []);

  // 如果有错误，显示原始代码
  if (error) {
    return (
      <View style={[styles.container, { backgroundColor: colors.surfaceVariant }]}>
        <View style={styles.errorHeader}>
          <MaterialIcons name="error-outline" size={20} color={colors.error} />
          <Text style={[styles.errorTitle, { color: colors.error }]}>
            {t('mermaidChart.renderFailed')}
          </Text>
        </View>
        <View style={[styles.codeBlock, { backgroundColor: colors.background }]}>
          <Text style={[styles.codeText, { color: colors.onSurface }]}>
            {chart}
          </Text>
        </View>
      </View>
    );
  }

  return (
    <>
      <TouchableOpacity
        style={[styles.container, { backgroundColor: colors.surfaceVariant }]}
        onPress={() => setFullscreen(true)}
        activeOpacity={0.9}
      >
        {/* 头部 */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <MaterialIcons name="account-tree" size={18} color={colors.primary} />
            <Text style={[styles.title, { color: colors.primary }]}>{t('mermaidChart.title')}</Text>
          </View>
          <MaterialIcons name="fullscreen" size={20} color={colors.onSurfaceVariant} />
        </View>

        {/* 图表内容 */}
        <View style={[styles.chartContainer, { height }]}>
          {loading && (
            <View style={styles.loadingOverlay}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.onSurfaceVariant }]}>
                {t('mermaidChart.rendering')}
              </Text>
            </View>
          )}
          <WebView
            source={{ html: generateMermaidHtml(chart) }}
            style={[styles.webview, { height }]}
            onLoadEnd={handleLoadEnd}
            onError={handleError}
            onMessage={handleMessage}
            scrollEnabled={false}
            bounces={false}
            originWhitelist={['*']}
            injectedJavaScript={`
              (function() {
                const observer = new ResizeObserver((entries) => {
                  const height = entries[0].contentRect.height;
                  window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'height', value: height }));
                });
                const mermaidDiv = document.querySelector('.mermaid');
                if (mermaidDiv) {
                  observer.observe(mermaidDiv);
                }
              })();
            `}
          />
        </View>

        {/* 提示文字 */}
        <Text style={[styles.hint, { color: colors.onSurfaceVariant }]}>
          {t('mermaidChart.clickToEnlarge')}
        </Text>
      </TouchableOpacity>

      {/* 全屏查看 */}
      <Modal
        visible={fullscreen}
        transparent
        animationType="fade"
        onRequestClose={() => setFullscreen(false)}
      >
        <View style={[styles.modalContainer, { backgroundColor: 'rgba(0,0,0,0.9)' }]}>
          <IconButton
            icon="close"
            size={28}
            iconColor="#fff"
            style={styles.closeButton}
            onPress={() => setFullscreen(false)}
          />
          <WebView
            source={{ html: generateMermaidHtml(chart) }}
            style={styles.fullscreenWebview}
            scrollEnabled={true}
            bounces={true}
          />
        </View>
      </Modal>
    </>
  );
});

// 检测文本中的 Mermaid 代码块
export function extractMermaidBlocks(text: string): Array<{ type: 'text' | 'mermaid'; content: string }> {
  const mermaidRegex = /```mermaid\n([\s\S]*?)```/g;
  const parts: Array<{ type: 'text' | 'mermaid'; content: string }> = [];
  
  let lastIndex = 0;
  let match;
  
  while ((match = mermaidRegex.exec(text)) !== null) {
    // 添加前面的文本
    if (match.index > lastIndex) {
      parts.push({
        type: 'text',
        content: text.slice(lastIndex, match.index),
      });
    }
    
    // 添加 Mermaid 代码块
    parts.push({
      type: 'mermaid',
      content: match[1].trim(),
    });
    
    lastIndex = match.index + match[0].length;
  }
  
  // 添加剩余的文本
  if (lastIndex < text.length) {
    parts.push({
      type: 'text',
      content: text.slice(lastIndex),
    });
  }
  
  return parts.length > 0 ? parts : [{ type: 'text', content: text }];
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 12,
    marginVertical: 8,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  title: {
    fontSize: 13,
    fontWeight: '600',
  },
  chartContainer: {
    position: 'relative',
    backgroundColor: '#fff',
  },
  webview: {
    backgroundColor: 'transparent',
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.9)',
    zIndex: 1,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 13,
  },
  hint: {
    textAlign: 'center',
    fontSize: 12,
    paddingVertical: 8,
  },
  errorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: 12,
  },
  errorTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  codeBlock: {
    padding: 12,
    margin: 12,
    marginTop: 0,
    borderRadius: 8,
  },
  codeText: {
    fontFamily: 'monospace',
    fontSize: 12,
    lineHeight: 18,
  },
  modalContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  fullscreenWebview: {
    width: SCREEN_WIDTH,
    height: SCREEN_HEIGHT - 100,
    marginTop: 50,
  },
  closeButton: {
    position: 'absolute',
    top: 40,
    right: 20,
    backgroundColor: 'rgba(255,255,255,0.2)',
  },
});
