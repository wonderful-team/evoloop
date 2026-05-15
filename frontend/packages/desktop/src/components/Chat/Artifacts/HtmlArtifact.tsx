import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from "@evoloop/shared/components/ui/card";
import { Code2, ExternalLink, Maximize2 } from 'lucide-react';
import { Button } from "@evoloop/shared/components/ui/button";
import { useTranslation } from 'react-i18next';

interface HtmlArtifactProps {
  data: {
    title?: string;
    html: string;
    css?: string;
    js?: string;
    height?: number;
  };
}

export const HtmlArtifact: React.FC<HtmlArtifactProps> = ({ data }) => {
  const { t } = useTranslation();
  const iframeRef = React.useRef<HTMLIFrameElement>(null);

  const fullHtml = React.useMemo(() => {
    return `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8">
          <style>
            body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
            ${data.css || ''}
          </style>
        </head>
        <body>
          ${data.html}
          <script>${data.js || ''}<\/script>
        </body>
      </html>
    `;
  }, [data.html, data.css, data.js]);

  React.useEffect(() => {
    if (iframeRef.current) {
      const doc = iframeRef.current.contentDocument;
      if (doc) {
        doc.open();
        doc.write(fullHtml);
        doc.close();
      }
    }
  }, [fullHtml]);

  return (
    <div className="w-full my-6 border border-[var(--doc-border)] bg-muted/5 rounded-xl overflow-hidden transition-all duration-500 animate-in fade-in slide-in-from-top-2">
      <div className="py-3 px-5 border-b border-[var(--doc-border)] bg-muted/10 flex flex-row items-center justify-between group/html">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-primary/50 mb-0.5">UI Artifact</span>
          <h3 className="text-sm font-bold tracking-tight">
            {data.title || t('chat.artifact.htmlPreview', 'HTML Preview')}
          </h3>
        </div>
        <div className="flex items-center gap-2 opacity-0 group-hover/html:opacity-100 transition-opacity">
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full" title={t('common.open')}>
            <ExternalLink className="w-4 h-4 text-muted-foreground" />
          </Button>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full" title={t('common.expand')}>
            <Maximize2 className="w-4 h-4 text-muted-foreground" />
          </Button>
        </div>
      </div>
      <div className="bg-white dark:bg-zinc-900 overflow-hidden relative" style={{ height: `${data.height || 400}px` }}>
        <iframe
          ref={iframeRef}
          title="HTML Preview"
          className="w-full h-full border-none"
          sandbox="allow-scripts"
        />
      </div>
    </div>
  );
};
