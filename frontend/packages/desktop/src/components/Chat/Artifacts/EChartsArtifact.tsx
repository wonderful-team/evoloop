import React, { useMemo, useEffect, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card";
import { useTranslation } from 'react-i18next';

interface EChartsArtifactProps {
  data: {
    title?: string;
    option: any;
  };
}

export const EChartsArtifact: React.FC<EChartsArtifactProps> = ({ data }) => {
  const { t } = useTranslation();
  const [isDark, setIsDark] = useState(false);

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

  const chartTheme = isDark ? 'dark' : 'light';

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

  return (
    <Card className="w-full my-4 border-primary/10 bg-card/50 backdrop-blur-sm overflow-hidden shadow-lg">
      <CardHeader className="py-3 px-4 border-b border-border/40">
        <CardTitle className="text-sm font-semibold tracking-tight">
          {data.title || t('chat.artifact.chart', 'Statistical Analysis')}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="w-full h-[350px] md:h-[400px]">
          <ReactECharts
            option={mergedOption}
            theme={chartTheme}
            style={{ height: '100%', width: '100%' }}
            opts={{ renderer: 'svg' }} // SVG renderer for sharper lines on retina
            notMerge={true}
            lazyUpdate={true}
          />
        </div>
      </CardContent>
    </Card>
  );
};
