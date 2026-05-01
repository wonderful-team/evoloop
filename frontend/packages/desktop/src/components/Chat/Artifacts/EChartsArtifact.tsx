import React, { useMemo, useEffect, useState, useRef, Component, type ReactNode } from 'react';
import ReactECharts from 'echarts-for-react';
import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card";
import { Button } from "@evoloop/shared/components/ui/button";
import { useTranslation } from 'react-i18next';
import { Download, AlertCircle } from 'lucide-react';

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
          {data.title || t('chat.artifact.chartError', 'Chart Rendering Error')}
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

export const EChartsArtifact: React.FC<EChartsArtifactProps> = ({ data }) => {
  const { t } = useTranslation();
  const [isDark, setIsDark] = useState(false);
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

  // Handle window resize
  useEffect(() => {
    const handleResize = () => {
      const instance = chartRef.current?.getEchartsInstance();
      if (instance) {
        instance.resize();
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const chartTheme = isDark ? 'dark' : 'light';

  const validation = useMemo(() => validateOption(data.option), [data.option]);

  // Apply default styles to the option object if not present
  const mergedOption = useMemo(() => {
    const baseOption = {
      backgroundColor: 'transparent',
      textStyle: {
        fontFamily: 'Inter, system-ui, sans-serif',
      },
      tooltip: {
        trigger: 'axis',
        borderRadius: 8,
        padding: 10,
        backgroundColor: isDark ? 'rgba(32, 32, 32, 0.9)' : 'rgba(255, 255, 255, 0.9)',
        borderColor: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)',
        textStyle: {
          color: isDark ? '#f4f4f5' : '#18181b',
        }
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '3%',
        containLabel: true
      },
      animation: true,
      animationDuration: 1000,
      animationEasing: 'cubicOut'
    };

    return { ...baseOption, ...data.option };
  }, [data.option, isDark]);

  const handleSaveImage = () => {
    const instance = chartRef.current?.getEchartsInstance();
    if (instance) {
      try {
        const url = instance.getDataURL({
          type: 'png',
          pixelRatio: 2,
          backgroundColor: isDark ? '#18181b' : '#ffffff',
        });
        const link = document.createElement('a');
        link.download = `${data.title || 'chart'}.png`;
        link.href = url;
        link.click();
      } catch (e) {
        console.error('Failed to save chart image:', e);
      }
    }
  };

  const chartHeight = data.height ?? 350;

  if (!validation.valid) {
    return <EChartsErrorFallback data={data} />;
  }

  return (
    <EChartsErrorBoundary fallback={<EChartsErrorFallback data={data} />}>
      <div className="w-full my-6 border border-[var(--doc-border)] bg-muted/5 rounded-xl overflow-hidden transition-all duration-500 animate-in fade-in slide-in-from-top-2">
        <div className="py-3 px-5 border-b border-[var(--doc-border)] bg-muted/10 flex flex-row items-center justify-between group/chart">
          <div className="flex flex-col">
            <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary/50 mb-0.5">Visual Data Artifact</span>
            <h3 className="text-sm font-bold tracking-tight">
                {data.title || t('chat.artifact.chart', 'Statistical Analysis')}
            </h3>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-full bg-background/50 hover:bg-background shadow-sm transition-all opacity-0 group-hover/chart:opacity-100"
            onClick={handleSaveImage}
            title={t('chat.artifact.saveImage', 'Save as image')}
          >
            <Download className="w-4 h-4 text-muted-foreground hover:text-primary transition-colors" />
          </Button>
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
