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
    <Card className="w-full my-4 border-destructive/20 bg-destructive/5 overflow-hidden">
      <CardHeader className="py-3 px-4">
        <CardTitle className="text-sm font-semibold flex items-center gap-2 text-destructive">
          <AlertCircle className="w-4 h-4" />
          {data.title || t('chat.artifact.chartError', 'Chart Rendering Error')}
        </CardTitle>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <p className="text-xs text-muted-foreground mb-2">
          {t('chat.artifact.invalidChartOption', 'The chart configuration is invalid or incomplete.')}
        </p>
        <pre className="text-[10px] bg-muted/50 p-2 rounded overflow-auto max-h-[200px]">
          {JSON.stringify(data.option, null, 2)}
        </pre>
      </CardContent>
    </Card>
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
      <Card className="w-full my-4 border-primary/10 bg-card/50 backdrop-blur-sm overflow-hidden shadow-lg">
        <CardHeader className="py-3 px-4 border-b border-border/40 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold tracking-tight">
            {data.title || t('chat.artifact.chart', 'Statistical Analysis')}
          </CardTitle>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={handleSaveImage}
            title={t('chat.artifact.saveImage', 'Save as image')}
          >
            <Download className="w-3.5 h-3.5 text-muted-foreground hover:text-foreground" />
          </Button>
        </CardHeader>
        <CardContent className="p-0">
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
        </CardContent>
      </Card>
    </EChartsErrorBoundary>
  );
};
