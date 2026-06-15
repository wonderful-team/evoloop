import React, { useMemo, useEffect, useState, useRef, Component, type ReactNode } from 'react';
import * as echarts from 'echarts';
import ReactECharts from 'echarts-for-react';
import chinaMapData from '@/assets/maps/china.json';

// 注册中国地图数据，解决 "Map china not exists" 报错
echarts.registerMap('china', chinaMapData as any);

// Register custom themes for Evoloop to standardize default styles, fonts, and dark mode adaptation natively
const themeLight = {
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
  },
  tooltip: {
    trigger: 'axis',
    borderRadius: 8,
    padding: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.95)',
    borderColor: 'rgba(0, 0, 0, 0.1)',
    textStyle: {
      color: '#18181b',
    }
  },
  legend: {
    textStyle: {
      color: '#18181b'
    }
  }
};

const themeDark = {
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
  },
  tooltip: {
    trigger: 'axis',
    borderRadius: 8,
    padding: 10,
    backgroundColor: 'rgba(32, 32, 32, 0.95)',
    borderColor: 'rgba(255, 255, 255, 0.1)',
    textStyle: {
      color: '#f4f4f5',
    }
  },
  legend: {
    textStyle: {
      color: '#f4f4f5'
    }
  }
};

echarts.registerTheme('evoloop-light', themeLight);
echarts.registerTheme('evoloop-dark', themeDark);

import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card";
import { Button } from "@evoloop/shared/components/ui/button";
import { useTranslation } from 'react-i18next';
import { Copy, Check, Download, AlertCircle } from 'lucide-react';
import { toast } from "sonner";
import { isTauri } from "@/lib/tauri";

interface EChartsArtifactProps {
  data: {
    title?: string;
    option: any;
    height?: number;
  };
}

// Error Boundary for ECharts rendering failures
class EChartsErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { hasError: boolean }> {
  constructor(props: { fallback: ReactNode; children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

function EChartsErrorFallback({ data }: { data: EChartsArtifactProps['data'] }) {
  const { t } = useTranslation();
  return (
    <div className="w-full my-6 border border-destructive/20 bg-destructive/5 rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 bg-destructive/10 border-b border-destructive/10 text-destructive text-sm font-bold">
          <AlertCircle className="w-4 h-4" />
          {typeof data.title === 'string' ? data.title : t('chat.artifact.chartError', 'Chart Rendering Error')}
        </div>
      <div className="p-4">
        <p className="text-xs text-muted-foreground mb-3 font-medium">
          {t('chat.artifact.invalidChartOption', 'The chart configuration is invalid or incomplete.')}
        </p>
        <pre className="text-[10px] bg-background/50 p-3 rounded-lg border border-destructive/10 overflow-auto max-h-[200px] font-mono leading-relaxed opacity-70">
          {JSON.stringify(data.option, null, 2)}
        </pre>
      </div>
    </div>
  );
}

function validateOption(option: any): { valid: boolean; reason?: string } {
  if (!option || typeof option !== 'object') {
    return { valid: false, reason: 'option is not an object' };
  }
  if (!Array.isArray(option.series)) {
    return { valid: false, reason: 'option.series is not an array' };
  }
  if (option.series.length === 0) {
    return { valid: false, reason: 'option.series is empty' };
  }
  return { valid: true };
}

/**
 * Preprocess and sanitize option to:
 * 1. Safely remove title option (avoid duplicating title inside canvas vs card header)
 * 2. Configure default grid or smart-adjust grid bottoms if there's a legend to avoid label cutoffs
 * 3. Keep option structures clean for theme blending
 */
function sanitizeOption(option: any): any {
  if (!option || typeof option !== 'object') {
    return { series: [] };
  }

  const sanitized = { ...option };

  // Delete option's internal title entirely to avoid rendering duplication
  delete sanitized.title;

  const hasLegend = !!sanitized.legend;

  // Safe grid adjustments
  if (sanitized.grid) {
    if (Array.isArray(sanitized.grid)) {
      sanitized.grid = sanitized.grid.map((g: any) => {
        if (g && typeof g === 'object') {
          const newG = { containLabel: true, ...g };
          if (newG.bottom === '3%' && hasLegend) {
            newG.bottom = '12%';
          }
          return newG;
        }
        return g;
      });
    } else if (typeof sanitized.grid === 'object') {
      const newGrid = { containLabel: true, ...sanitized.grid };
      if (newGrid.bottom === '3%' && hasLegend) {
        newGrid.bottom = '12%';
      }
      sanitized.grid = newGrid;
    }
  } else {
    sanitized.grid = {
      left: '3%',
      right: '4%',
      bottom: hasLegend ? '12%' : '8%',
      containLabel: true
    };
  }

  // Sensible animation overrides if not specified by user
  if (sanitized.animation === undefined) {
    sanitized.animation = true;
  }
  if (sanitized.animationDuration === undefined) {
    sanitized.animationDuration = 1000;
  }
  if (sanitized.animationEasing === undefined) {
    sanitized.animationEasing = 'cubicOut';
  }

  return sanitized;
}

const EChartsArtifactInner: React.FC<EChartsArtifactProps> = ({ data }) => {
  const { t } = useTranslation();
  const [isDark, setIsDark] = useState(false);
  const [copied, setCopied] = useState(false);
  const chartRef = useRef<ReactECharts>(null);

  // Sync with system or app theme
  useEffect(() => {
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.attributeName === 'class') {
          setIsDark(document.documentElement.classList.contains('dark'));
        }
      });
    });

    observer.observe(document.documentElement, { attributes: true });
    setIsDark(document.documentElement.classList.contains('dark'));

    return () => observer.disconnect();
  }, []);

  // Handle window resize — debounced to avoid calling resize during ECharts main process
  useEffect(() => {
    let rafId: number;
    const handleResize = () => {
      cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        const instance = chartRef.current?.getEchartsInstance();
        if (instance) {
          instance.resize();
        }
      });
    };

    window.addEventListener('resize', handleResize);
    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(rafId);
    };
  }, []);

  const chartTheme = isDark ? 'evoloop-dark' : 'evoloop-light';

  const validation = useMemo(() => validateOption(data.option), [data.option]);

  // Clean, thin-wrapper option preprocessing
  const mergedOption = useMemo(() => {
    return sanitizeOption(data.option);
  }, [data.option]);

  const handleSaveImage = async () => {
    const instance = chartRef.current?.getEchartsInstance();
    if (!instance) return;

    try {
      const defaultFilename = `${data.title || 'chart'}.png`;

      const dataUrl = instance.getDataURL({
        type: 'png',
        pixelRatio: 2,
        backgroundColor: isDark ? '#18181b' : '#ffffff',
      });

      if (isTauri()) {
        const { save } = await import("@tauri-apps/plugin-dialog")
        const { writeFile } = await import("@tauri-apps/plugin-fs")
        const filePath = await save({
          defaultPath: defaultFilename,
          filters: [{ name: 'Image', extensions: ['png'] }]
        });

        if (!filePath) return;

        const base64Data = dataUrl.split(',')[1];
        const binaryString = atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }

        await writeFile(filePath, bytes);
      } else {
        // Web fallback: trigger browser download
        const link = document.createElement('a');
        link.href = dataUrl;
        link.download = defaultFilename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
      }

      toast.success(t('common.saveSuccess'));
    } catch (e) {
      console.error('Failed to save chart image:', e);
      toast.error(t('common.saveFailed'));
    }
  };

  const chartHeight = data.height ?? 350;

  // Extract the title to display in the header: prioritize explicit string title, then title.text from options
  let optionTitleText = '';
  if (data.option?.title) {
    if (Array.isArray(data.option.title)) {
      optionTitleText = data.option.title[0]?.text || '';
    } else {
      optionTitleText = data.option.title.text || '';
    }
  }

  const displayTitle = (typeof data.title === 'string' && data.title !== 'echarts')
    ? data.title 
    : (optionTitleText || t('chat.artifact.chart', 'Statistical Analysis'));

  if (!validation.valid) {
    return <EChartsErrorFallback data={data} />;
  }

  return (
    <EChartsErrorBoundary fallback={<EChartsErrorFallback data={data} />}>
      <div className="w-full my-6 border border-[var(--doc-border)] bg-muted/5 rounded-xl overflow-hidden transition-all duration-500 animate-in fade-in slide-in-from-top-2">
        <div className="py-3 px-5 border-b border-[var(--doc-border)] bg-muted/10 flex flex-row items-center justify-between group/chart">
          <div className="flex flex-col">
            <h3 className="text-sm font-bold tracking-tight">
                {displayTitle}
            </h3>
          </div>
          <div className="flex items-center gap-2 opacity-0 group-hover/chart:opacity-100 transition-opacity">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full bg-background/50 hover:bg-background shadow-sm"
              onClick={() => {
                navigator.clipboard.writeText(JSON.stringify(data.option, null, 2));
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
              }}
              title={t('common.copy')}
            >
              {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4 text-muted-foreground" />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-full bg-background/50 hover:bg-background shadow-sm"
              onClick={handleSaveImage}
              title={t('chat.artifact.saveImage', 'Save as image')}
            >
              <Download className="w-4 h-4 text-muted-foreground hover:text-primary transition-colors" />
            </Button>
          </div>
        </div>
        <div className="p-4 bg-background/40 backdrop-blur-sm">
          <div className="w-full" style={{ height: `${chartHeight}px` }}>
            <ReactECharts
              ref={chartRef}
              option={mergedOption}
              theme={chartTheme}
              style={{ height: '100%', width: '100%' }}
              opts={{ renderer: 'svg' }}
              notMerge={true}
              lazyUpdate={true}
            />
          </div>
        </div>
      </div>
    </EChartsErrorBoundary>
  );
};

/**
 * Stable memo wrapper: only re-render when data.option reference or data.title changes.
 * Combined with Object.freeze + cache in MessageContent, this prevents the chart
 * from re-mounting / re-rendering while SSE is still streaming text after the chart block.
 */
export const EChartsArtifact = React.memo(
  EChartsArtifactInner,
  (prev, next) =>
    prev.data.option === next.data.option &&
    prev.data.title === next.data.title &&
    prev.data.height === next.data.height
);
