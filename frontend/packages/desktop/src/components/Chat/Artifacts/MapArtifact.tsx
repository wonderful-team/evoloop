import React, { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card";
import { useTranslation } from 'react-i18next';
import { MapPin, AlertCircle } from 'lucide-react';

declare global {
  interface Window {
    AMap?: any;
    _AMapLoadingPromise?: Promise<void>;
    _AMapSecurityConfig?: { securityJsCode?: string };
  }
}

interface MapMarker {
  position?: { lng: number; lat: number };
  address?: string;
  title?: string;
}

interface MapRoute {
  from: string | { lng: number; lat: number };
  to: string | { lng: number; lat: number };
  mode?: 'driving' | 'walking' | 'riding' | 'transit';
}

interface MapArtifactProps {
  data: {
    title?: string;
    center?: { lng: number; lat: number };
    zoom?: number;
    markers?: MapMarker[];
    route?: MapRoute;
    height?: number;
  };
}

const AMAP_KEY = import.meta.env.VITE_AMAP_KEY || '';

function loadAMapScript(): Promise<void> {
  if (window.AMap) return Promise.resolve();
  if (window._AMapLoadingPromise) return window._AMapLoadingPromise;

  window._AMapLoadingPromise = new Promise((resolve, reject) => {
    if (!AMAP_KEY) {
      reject(new Error('AMap Key is not configured'));
      return;
    }
    const script = document.createElement('script');
    script.type = 'text/javascript';
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${AMAP_KEY}`;
    script.onerror = () => reject(new Error('Failed to load AMap script'));
    script.onload = () => {
      // Wait a tick for AMap global to be ready
      setTimeout(() => {
        if (window.AMap) resolve();
        else reject(new Error('AMap global not available after script load'));
      }, 100);
    };
    document.head.appendChild(script);
  });

  return window._AMapLoadingPromise;
}

export const MapArtifact: React.FC<MapArtifactProps> = ({ data }) => {
  const { t } = useTranslation();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isCancelled = false;

    const initMap = async () => {
      try {
        await loadAMapScript();
        if (isCancelled || !containerRef.current) return;

        const AMap = window.AMap;
        const map = new AMap.Map(containerRef.current, {
          zoom: data.zoom || 12,
          center: data.center ? [data.center.lng, data.center.lat] : undefined,
        });
        mapRef.current = map;

        // Add markers
        if (data.markers && data.markers.length > 0) {
          const markerPromises = data.markers.map(async (m) => {
            let position: number[];
            if (m.position) {
              position = [m.position.lng, m.position.lat];
            } else if (m.address) {
              // Geocode address
              try {
                const geocoder = new AMap.Geocoder();
                const result = await new Promise<any>((resolve, reject) => {
                  geocoder.getLocation(m.address, (status: string, res: any) => {
                    if (status === 'complete' && res.geocodes?.length > 0) {
                      resolve(res.geocodes[0].location);
                    } else {
                      reject(new Error(`Geocode failed for: ${m.address}`));
                    }
                  });
                });
                position = [result.lng, result.lat];
              } catch {
                return null;
              }
            } else {
              return null;
            }

            const marker = new AMap.Marker({
              position,
              title: m.title || '',
            });

            if (m.title) {
              const infoWindow = new AMap.InfoWindow({
                content: `<div style="padding:4px 8px;font-size:13px;">${m.title}</div>`,
                offset: new AMap.Pixel(0, -30),
              });
              marker.on('click', () => infoWindow.open(map, marker.getPosition()));
            }

            return marker;
          });

          const markers = (await Promise.all(markerPromises)).filter(Boolean);
          map.add(markers);

          // Auto-fit bounds if no center specified
          if (!data.center && markers.length > 0) {
            map.setFitView();
          }
        }

        // Add route
        if (data.route) {
          const { from, to, mode = 'driving' } = data.route;
          const pluginName = mode === 'transit' ? 'AMap.Transfer' :
                             mode === 'walking' ? 'AMap.Walking' :
                             mode === 'riding' ? 'AMap.Riding' :
                             'AMap.Driving';

          await new Promise<void>((resolve) => {
            AMap.plugin([pluginName], () => resolve());
          });

          const RouteClass = AMap[pluginName.split('.')[1]];
          const routeInstance = new RouteClass({
            map,
            panel: false,
          });

          const resolvePoint = async (p: string | { lng: number; lat: number }): Promise<any> => {
            if (typeof p === 'string') {
              const geocoder = new AMap.Geocoder();
              return new Promise((res, rej) => {
                geocoder.getLocation(p, (status: string, res2: any) => {
                  if (status === 'complete' && res2.geocodes?.length > 0) {
                    res(res2.geocodes[0].location);
                  } else {
                    rej(new Error(`Geocode failed: ${p}`));
                  }
                });
              });
            }
            return new AMap.LngLat(p.lng, p.lat);
          };

          try {
            const origin = await resolvePoint(from);
            const destination = await resolvePoint(to);
            routeInstance.search(origin, destination);
          } catch (e) {
            console.warn('Route search failed:', e);
          }
        }

        if (!isCancelled) setLoading(false);
      } catch (e: any) {
        if (!isCancelled) {
          setError(e?.message || 'Map initialization failed');
          setLoading(false);
        }
      }
    };

    initMap();

    return () => {
      isCancelled = true;
      if (mapRef.current) {
        mapRef.current.destroy();
        mapRef.current = null;
      }
    };
  }, [data]);

  const height = data.height || 400;

  if (error) {
    return (
      <Card className="w-full my-4 border-destructive/20 bg-destructive/5 overflow-hidden">
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-sm font-semibold flex items-center gap-2 text-destructive">
            <AlertCircle className="w-4 h-4" />
            {data.title || t('chat.artifact.mapError', 'Map Error')}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <p className="text-xs text-muted-foreground">{error}</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full my-4 border-primary/10 bg-card/50 backdrop-blur-sm overflow-hidden shadow-lg">
      <CardHeader className="py-3 px-4 border-b border-border/40 flex flex-row items-center gap-2">
        <MapPin className="w-4 h-4 text-primary" />
        <CardTitle className="text-sm font-semibold tracking-tight">
          {data.title || t('chat.artifact.map', 'Map')}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-muted/30 z-10">
            <div className="flex flex-col items-center gap-2">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              <span className="text-xs text-muted-foreground">{t('chat.artifact.loadingMap', 'Loading map...')}</span>
            </div>
          </div>
        )}
        <div ref={containerRef} style={{ width: '100%', height: `${height}px` }} />
      </CardContent>
    </Card>
  );
};
