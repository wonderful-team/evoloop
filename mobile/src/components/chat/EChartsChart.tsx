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

interface EChartsChartProps {
  data: {
    title?: string;
    option: any;
  };
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

const generateEChartsHtml = (option: any, isDark: boolean) => {
  const theme = isDark ? 'dark' : '';
  const bgColor = isDark ? '#18181b' : '#ffffff';
  const textColor = isDark ? '#f4f4f5' : '#18181b';

  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      margin: 0;
      padding: 0;
      background: ${bgColor};
      overflow: hidden;
    }
    #chart {
      width: 100vw;
      height: 100vh;
    }
  </style>
</head>
<body>
  <div id="chart"></div>
  <script>
    (function() {
      try {
        const option = ${JSON.stringify(option)};
        // Apply base styles
        option.backgroundColor = option.backgroundColor || 'transparent';
        if (!option.textStyle) option.textStyle = {};
        option.textStyle.fontFamily = 'Inter, system-ui, sans-serif';

        const chart = echarts.init(document.getElementById('chart'), '${theme}');
        chart.setOption(option);

        // Report height after render
        const reportHeight = function() {
          const canvas = document.querySelector('canvas');
          const height = canvas ? canvas.scrollHeight : document.body.scrollHeight;
          window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'height', value: height }));
        };
        setTimeout(reportHeight, 300);
        setTimeout(reportHeight, 800);

        // Handle resize
        window.addEventListener('resize', function() {
          chart.resize();
        });
      } catch (err) {
        window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'error', message: err.message }));
      }
    })();
  </script>
</body>
</html>
`;
};

export const EChartsChart = memo(function EChartsChart({ data }: EChartsChartProps) {
  const { colors, isDark } = useTheme();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);

  const [error, setError] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [height, setHeight] = useState(280);

  const handleLoadEnd = useCallback(() => {
    setLoading(false);
  }, []);

  const handleError = useCallback(() => {
    setError(true);
    setLoading(false);
  }, []);

  const handleMessage = useCallback((event: { nativeEvent: { data: string } }) => {
    try {
      const msg = JSON.parse(event.nativeEvent.data);
      if (msg.type === 'height' && msg.value) {
        setHeight(Math.max(200, Math.min(msg.value, 500)));
      }
      if (msg.type === 'error') {
        setError(true);
        setLoading(false);
      }
    } catch {
      // ignore parse errors
    }
  }, []);

  if (error) {
    return (
      <View style={[styles.container, { backgroundColor: colors.surfaceVariant }]}>
        <View style={styles.errorHeader}>
          <MaterialIcons name="error-outline" size={20} color={colors.error} />
          <Text style={[styles.errorTitle, { color: colors.error }]}>
            {t('echartsChart.renderFailed')}
          </Text>
        </View>
        <View style={[styles.codeBlock, { backgroundColor: colors.background }]}>
          <Text style={[styles.codeText, { color: colors.onSurface }]}>
            {data.title || 'ECharts'}
          </Text>
        </View>
      </View>
    );
  }

  const finalOption = data.option || data;
  const htmlContent = generateEChartsHtml(finalOption, isDark);

  // 处理标题显示逻辑：支持字符串或 ECharts 标题对象
  const rawTitle = data.title || (data.option ? data.option.title : undefined);
  const displayTitle = typeof rawTitle === 'object' ? (rawTitle as any).text : rawTitle;


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
            <MaterialIcons name="bar-chart" size={18} color={colors.primary} />
            <Text style={[styles.title, { color: colors.primary }]}>
              {displayTitle || t('chat.codeBlock.echartsChart')}
            </Text>
          </View>

          <MaterialIcons name="fullscreen" size={20} color={colors.onSurfaceVariant} />
        </View>

        {/* 图表内容 */}
        <View style={[styles.chartContainer, { height }]}>
          {loading && (
            <View style={styles.loadingOverlay}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.onSurfaceVariant }]}>
                {t('echartsChart.rendering')}
              </Text>
            </View>
          )}
          <WebView
            source={{ html: htmlContent }}
            style={[styles.webview, { height }]}
            onLoadEnd={handleLoadEnd}
            onError={handleError}
            onMessage={handleMessage}
            scrollEnabled={false}
            bounces={false}
            originWhitelist={['*']}
          />
        </View>

        {/* 提示文字 */}
        <Text style={[styles.hint, { color: colors.onSurfaceVariant }]}>
          {t('echartsChart.clickToEnlarge')}
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
            source={{ html: htmlContent }}
            style={styles.fullscreenWebview}
            scrollEnabled={true}
            bounces={true}
          />
        </View>
      </Modal>
    </>
  );
});

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
