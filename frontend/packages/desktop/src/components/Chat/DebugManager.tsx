import React from 'react';
import { Button } from "@evoloop/shared/components/ui/button";
import { 
  Trash2, 
  Layers, 
  Zap, 
  Play, 
  Settings2,
  Monitor,
  Database,
  CheckCircle2
} from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { generateMockMessages, simulateStreaming } from "./debug/mockData";
import { toast } from "sonner";
import { v4 as uuidv4 } from 'uuid';

export function DebugManager() {
  const { messages, clearContent } = useChatStore();
  const [isStreaming, setIsStreaming] = React.useState(false);
  
  const injectMocks = () => {
    const mocks = generateMockMessages();
    useChatStore.setState({ messages: mocks });
    toast.success("5大类21种形态全域消息块已注入");
  };

  const startStreamingSimulation = async () => {
    if (isStreaming) return;
    setIsStreaming(true);
    
    const msgId = uuidv4();
    const newMsg: any = {
      id: msgId,
      role: "ai",
      content: "",
      thinking: "正在启动流式输出模拟...",
      status: "streaming",
      timestamp: new Date().toISOString(),
    };
    useChatStore.setState((s) => ({ messages: [...s.messages, newMsg] }));

    try {
      await simulateStreaming((content) => {
        useChatStore.setState((s) => ({
          messages: s.messages.map((m) => m.id === msgId ? { ...m, content } : m)
        }));
      });
      useChatStore.setState((s) => ({
        messages: s.messages.map((m) => m.id === msgId ? { ...m, status: "completed" } : m)
      }));
      toast.success("流式输出完成");
    } catch (err) {
      useChatStore.setState((s) => ({
        messages: s.messages.map((m) => m.id === msgId ? { ...m, status: "failed" } : m)
      }));
      toast.error("流式输出失败");
    } finally {
      setIsStreaming(false);
    }
  };

  const simulateHITL = (type: 'approval' | 'text_input' | 'choice' | 'confirmation' | 'project_switch' | 'file_select' = 'approval') => {
    let prompt = "";
    let options: string[] | undefined = undefined;
    
    switch(type) {
      case 'approval': prompt = "是否批准部署到生产环境？"; break;
      case 'text_input': prompt = "请输入你的 API Key 以继续："; break;
      case 'choice': 
        prompt = "请选择你要执行的重构策略："; 
        options = ["快速重构", "深度优化", "保守修复"]; 
        break;
      case 'confirmation': prompt = "检测到 node_modules 异常，是否执行强制清理？"; break;
      case 'project_switch': prompt = "当前操作跨越了多个目录，建议切换到更合适的项目上下文："; break;
      case 'file_select': prompt = "请选择需要作为上下文参考的本地源代码文件："; break;
    }

    useChatStore.setState({
      status: "interrupted",
      humanRequest: {
        id: uuidv4(),
        type,
        prompt,
        context: "此请求来自 Agent 的核心安全策略校验。",
        options,
        status: "waiting_human"
      }
    });
    toast.success(`${type} 类型的 HITL 已注入`);
  };

  const clearMessages = () => {
    clearContent();
    useChatStore.setState({ humanRequest: null, status: "idle" });
    toast.info("会话已清空");
  };

  const isDev = import.meta.env.DEV;
  if (!isDev) return null;

  return (
    <div className="fixed bottom-24 left-6 z-[100] flex flex-col gap-2 scale-90 origin-bottom-left hover:scale-100 transition-all duration-300">
      <div className="flex flex-col gap-1.5 p-2.5 bg-zinc-900/90 backdrop-blur-xl border border-white/10 shadow-2xl rounded-2xl w-56">
        {/* Header */}
        <div className="px-2 py-1 mb-1 border-b border-white/5 flex items-center justify-between">
          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest flex items-center gap-2">
            <Settings2 className="h-3 w-3 text-primary animate-pulse" />
            Control Center
          </span>
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
            <div className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          </div>
        </div>
        
        {/* Actions Group */}
        <div className="space-y-1">
          <DebugButton 
            icon={<Layers className="h-3.5 w-3.5" />} 
            label="注入全能消息块" 
            onClick={injectMocks}
            variant="primary"
          />
          
          <DebugButton 
            icon={<Play className="h-3.5 w-3.5" />} 
            label="模拟 AI 流式输出" 
            onClick={startStreamingSimulation}
            disabled={isStreaming}
            loading={isStreaming}
          />

          <div className="grid grid-cols-3 gap-1">
            <DebugButton 
              icon={<CheckCircle2 className="h-3 w-3" />} 
              label="审批" 
              onClick={() => simulateHITL('approval')}
            />
            <DebugButton 
              icon={<Zap className="h-3 w-3" />} 
              label="确认" 
              onClick={() => simulateHITL('confirmation')}
            />
            <DebugButton 
              icon={<Layers className="h-3 w-3" />} 
              label="选择" 
              onClick={() => simulateHITL('choice')}
            />
            <DebugButton 
              icon={<Play className="h-3 w-3" />} 
              label="输入" 
              onClick={() => simulateHITL('text_input')}
            />
             <DebugButton 
              icon={<Monitor className="h-3 w-3" />} 
              label="切换" 
              onClick={() => simulateHITL('project_switch')}
            />
             <DebugButton 
              icon={<Database className="h-3 w-3" />} 
              label="文件" 
              onClick={() => simulateHITL('file_select')}
            />
          </div>
        </div>

        {/* System Group */}
        <div className="mt-1 pt-2 border-t border-white/5 space-y-1">
          <DebugButton 
            icon={<Trash2 className="h-3.5 w-3.5" />} 
            label="清空当前消息" 
            onClick={clearMessages}
            variant="danger"
          />
        </div>

        {/* Footer info */}
        <div className="mt-1 pt-1.5 flex justify-between items-center opacity-40 px-1">
          <div className="flex items-center gap-1">
            <Database className="h-2.5 w-2.5" />
            <span className="text-[9px] font-mono">{messages.length} MSGS</span>
          </div>
          <span className="text-[9px] font-mono font-bold uppercase tracking-tighter">V2.0-UNIVERSAL</span>
        </div>
      </div>
    </div>
  );
}

function DebugButton({ 
  icon, 
  label, 
  onClick, 
  variant = 'default', 
  disabled = false,
  loading = false
}: { 
  icon: React.ReactNode, 
  label: string, 
  onClick: () => void,
  variant?: 'default' | 'primary' | 'danger',
  disabled?: boolean,
  loading?: boolean
}) {
  const styles = {
    default: "hover:bg-white/5 text-zinc-300",
    primary: "hover:bg-primary/20 text-primary-foreground hover:text-primary",
    danger: "hover:bg-red-500/20 text-zinc-400 hover:text-red-400"
  };

  return (
    <Button 
      variant="ghost" 
      size="sm" 
      onClick={onClick}
      disabled={disabled}
      className={`w-full justify-start gap-2.5 h-9 px-3 rounded-xl transition-all active:scale-95 ${styles[variant]}`}
    >
      {loading ? <Zap className="h-3.5 w-3.5 animate-spin text-primary" /> : icon}
      <span className="text-[11px] font-medium tracking-tight">{label}</span>
    </Button>
  );
}
