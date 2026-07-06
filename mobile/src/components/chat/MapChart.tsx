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
import { AMAP_CONFIG } from '@/constants/config';

interface MapChartProps {
  data: {
    title?: string;
    center?: { lng: number; lat: number };
    zoom?: number;
    markers?: Array<{
      position?: { lng: number; lat: number };
      address?: string;
      title?: string;
    }>;
    route?: {
      from: string | { lng: number; lat: number };
      to: string | { lng: number; lat: number };
      mode?: 'driving' | 'walking' | 'riding' | 'transit';
    };
    height?: number;
  };
}

const { width: SCREEN_WIDTH, height: SCREEN_HEIGHT } = Dimensions.get('window');

const generateAMapHtml = (data: MapChartProps['data'], isDark: boolean, routeSearchFailedText: string) => {
  const key = AMAP_CONFIG.key || '74619d8469c894f09d84e55e8c9735d4'; // 兜底 Key 仅供调试
  const securityCode = 'f6b215886617a26f63f350c3132694b8'; // 高德安全密钥（必填）
  const bgColor = isDark ? '#18181b' : '#ffffff';
  const textColor = isDark ? '#f4f4f5' : '#18181b';

  return `
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <script type="text/javascript">
    window._AMapSecurityConfig = {
      securityJsCode: '${securityCode}',
    }
  </script>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { margin: 0; padding: 0; background: ${bgColor}; overflow: hidden; }
    #map { width: 100vw; height: 100vh; }
  </style>
</head>

<body>
  <div id="map"></div>
  <script src="https://webapi.amap.com/maps?v=2.0&key=${key}"></script>
  <script>
    (function() {
      try {
        const data = ${JSON.stringify(data)};
        const ROUTE_SEARCH_FAILED = ${JSON.stringify(routeSearchFailedText)};
        
        // 辅助函数：解析坐标格式 [lng, lat] 或 {lng, lat}
        const parsePos = (p) => {
          if (!p) return undefined;
          if (Array.isArray(p)) return p;
          return [p.lng || p.longitude, p.lat || p.latitude];
        };

        const map = new AMap.Map('map', {
          zoom: data.zoom || 12,
          center: parsePos(data.center),
        });

        // Add markers
        if (data.markers && data.markers.length > 0) {
          const addMarkers = async () => {
            const markerList = [];
            for (const m of data.markers) {
              let position = parsePos(m.position || m.pos);
              
              if (!position && m.address) {

                try {
                  const geocoder = new AMap.Geocoder();
                  const res = await new Promise((resolve, reject) => {
                    geocoder.getLocation(m.address, (status, result) => {
                      if (status === 'complete' && result.geocodes && result.geocodes.length > 0) {
                        resolve(result.geocodes[0].location);
                      } else {
                        reject();
                      }
                    });
                  });
                  position = [res.lng, res.lat];
                } catch (e) {
                  continue;
                }
              } else {
                continue;
              }

              const marker = new AMap.Marker({
                position: position,
                title: m.title || '',
              });

              if (m.title) {
                const infoWindow = new AMap.InfoWindow({
                  content: '<div style="padding:4px 8px;font-size:13px;">' + m.title + '</div>',
                  offset: new AMap.Pixel(0, -30),
                });
                marker.on('click', function() {
                  infoWindow.open(map, marker.getPosition());
                });
              }

              markerList.push(marker);
            }

            map.add(markerList);
            if (!data.center && markerList.length > 0) {
              map.setFitView();
            }
          };
          addMarkers();
        }

        // Add route
        if (data.route) {
          const mode = data.route.mode || 'driving';
          const pluginName = mode === 'transit' ? 'AMap.Transfer' :
                             mode === 'walking' ? 'AMap.Walking' :
                             mode === 'riding' ? 'AMap.Riding' :
                             'AMap.Driving';

          AMap.plugin([pluginName], function() {
            const RouteClass = AMap[pluginName.split('.')[1]];
            const routeInstance = new RouteClass({ map: map, panel: false });

            const resolvePoint = function(p) {
              return new Promise(function(res, rej) {
                if (typeof p === 'string') {
                  const geocoder = new AMap.Geocoder();
                  geocoder.getLocation(p, function(status, result) {
                    if (status === 'complete' && result.geocodes && result.geocodes.length > 0) {
                      res(result.geocodes[0].location);
                    } else {
                      rej();
                    }
                  });
                } else {
                  res(new AMap.LngLat(p.lng, p.lat));
                }
              });
            };

            Promise.all([
              resolvePoint(data.route.from),
              resolvePoint(data.route.to)
            ]).then(function(results) {
              routeInstance.search(results[0], results[1]);
            }).catch(function(e) {
              window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'routeError', message: ROUTE_SEARCH_FAILED }));
            });
          });
        }

        window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'ready' }));
      } catch (err) {
        window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'error', message: err.message }));
      }
    })();
  </script>
</body>
</html>
`;
};

export const MapChart = memo(function MapChart({ data }: MapChartProps) {
  const { colors, isDark } = useTheme();
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);

  const [error, setError] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

  const handleLoadEnd = useCallback(() => {
    // 仅在没有报错的情况下隐藏 Loading
  }, []);

  const handleError = useCallback(() => {
    setError(true);
    setErrorMsg(t('mapChart.webViewLoadError'));
    setLoading(false);
  }, [t]);

  const handleMessage = useCallback((event: { nativeEvent: { data: string } }) => {
    try {
      const msg = JSON.parse(event.nativeEvent.data);
      if (msg.type === 'ready') {
        setLoading(false);
        setError(false);
      }
      if (msg.type === 'error') {
        setError(true);
        setErrorMsg(msg.message);
        setLoading(false);
      }
    } catch {
      // ignore
    }
  }, []);

  if (error) {
    return (
      <View style={[styles.container, { backgroundColor: colors.surfaceVariant }]}>
        <View style={styles.errorHeader}>
          <MaterialIcons name="error-outline" size={20} color={colors.error} />
          <Text style={[styles.errorTitle, { color: colors.error }]}>
            {t('mapChart.loadFailed')}
          </Text>
        </View>
        <View style={[styles.codeBlock, { backgroundColor: colors.background }]}>
          <Text style={[styles.codeText, { color: colors.onSurface, fontSize: 11 }]}>
            {t('mapChart.errorPrefix')} {errorMsg || t('common.error.unknown')}
          </Text>
          <Text style={[styles.codeText, { color: colors.onSurfaceVariant, marginTop: 4 }]}>
            {t('mapChart.amapKeyTip')}
          </Text>
        </View>
      </View>
    );
  }


  const htmlContent = generateAMapHtml(data, isDark, t('mapChart.routeSearchFailed'));
  const height = data.height || 300;

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
            <MaterialIcons name="map" size={18} color={colors.primary} />
            <Text style={[styles.title, { color: colors.primary }]}>
              {data.title || t('mapChart.defaultTitle')}
            </Text>
          </View>
          <MaterialIcons name="fullscreen" size={20} color={colors.onSurfaceVariant} />
        </View>

        {/* 地图内容 */}
        <View style={[styles.mapContainer, { height }]}>
          {loading && (
            <View style={styles.loadingOverlay}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.onSurfaceVariant }]}>
                {t('mapChart.loading')}
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
          {t('mapChart.clickToEnlarge')}
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
  mapContainer: {
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
