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
      <div className="w-full my-6 border border-destructive/20 bg-destructive/5 rounded-xl overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 bg-destructive/10 border-b border-destructive/10 text-destructive text-sm font-bold">
            <AlertCircle className="w-4 h-4" />
            {data.title || t('chat.artifact.mapError', 'Map Error')}
          </div>
        <div className="p-4">
          <p className="text-xs text-muted-foreground font-medium">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full my-6 border border-[var(--doc-border)] bg-muted/5 rounded-xl overflow-hidden transition-all duration-500 animate-in fade-in slide-in-from-top-2">
      <div className="py-3 px-5 border-b border-[var(--doc-border)] bg-muted/10 flex flex-row items-center gap-3 group/map">
        <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <MapPin className="w-4 h-4" />
        </div>
        <div className="flex flex-col">
            <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary/50 mb-0.5">Geospatial Artifact</span>
            <h3 className="text-sm font-bold tracking-tight">
                {data.title || t('chat.artifact.map', 'Location Map')}
            </h3>
        </div>
      </div>
      <div className="p-0 relative bg-background/40 backdrop-blur-sm">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center bg-muted/30 z-10 backdrop-blur-[2px]">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-3 border-primary/30 border-t-primary rounded-full animate-spin" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60">{t('chat.artifact.loadingMap', 'Synchronizing Map Data...')}</span>
            </div>
          </div>
        )}
        <div ref={containerRef} style={{ width: '100%', height: `${height}px` }} className="grayscale-[0.2] hover:grayscale-0 transition-all duration-700" />
      </div>
    </div>
  );
};
