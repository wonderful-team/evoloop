import React from 'react';
import { Card, CardHeader, CardTitle, CardContent } from "@evoloop/shared/components/ui/card";
import { Atom, Code2, Copy, Check } from 'lucide-react';
import { Button } from "@evoloop/shared/components/ui/button";
import { useTranslation } from 'react-i18next';
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"

interface ReactArtifactProps {
  data: {
    title?: string;
    code: string;
    dependencies?: string[];
    componentName?: string;
  };
}

export const ReactArtifact: React.FC<ReactArtifactProps> = ({ data }) => {
  const { t } = useTranslation();
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(data.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="w-full my-6 border border-[var(--doc-border)] bg-muted/5 rounded-xl overflow-hidden transition-all duration-500 animate-in fade-in slide-in-from-top-2">
      <div className="py-3 px-5 border-b border-[var(--doc-border)] bg-muted/10 flex flex-row items-center justify-between group/react">
        <div className="flex flex-col">
          <h3 className="text-sm font-bold tracking-tight">
            {data.title || data.componentName || t('chat.artifact.reactComponent', 'React Component')}
          </h3>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-2 rounded-lg bg-background/50 hover:bg-background shadow-sm border border-border/40"
            onClick={handleCopy}
          >
            {copied ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5 text-muted-foreground" />}
            <span className="text-xs">{copied ? t('common.copied') : t('common.copy')}</span>
          </Button>
        </div>
      </div>

      <div className="p-0 bg-[#1e1e1e] relative">
        <div className="absolute top-3 right-4 flex items-center gap-2 z-10 pointer-events-none">
          {data.dependencies?.map(dep => (
            <span key={dep} className="px-1.5 py-0.5 bg-white/5 border border-white/10 rounded text-[9px] text-white/40 font-mono">
              {dep}
            </span>
          ))}
          <Atom className="w-4 h-4 text-sky-400 opacity-50" />
        </div>

        <div className="max-h-[400px] overflow-auto no-scrollbar">
          <SyntaxHighlighter
            style={vscDarkPlus as any}
            language="tsx"
            PreTag="div"
            customStyle={{
              margin: 0,
              padding: '20px',
              borderRadius: 0,
              fontSize: "12px",
              backgroundColor: 'transparent',
            }}
          >
            {data.code}
          </SyntaxHighlighter>
        </div>
      </div>

      <div className="px-5 py-2.5 bg-muted/10 border-t border-[var(--doc-border)] flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground font-medium">
          {data.componentName || 'Component'} • {data.code.split('\n').length} lines
        </span>
        <div className="flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
          <span className="text-[10px] text-muted-foreground font-bold tracking-tight">STANDARDIZED V1</span>
        </div>
      </div>
    </div>
  );
};
