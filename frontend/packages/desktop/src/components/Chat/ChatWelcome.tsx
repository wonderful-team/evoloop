import React from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Bot, 
  Cpu, 
  Smartphone, 
  Zap, 
  Brain, 
  LayoutGrid, 
  Dna, 
  Wand2, 
  PlusCircle, 
  Search, 
  ListTodo, 
  ArrowRight,
  Activity,
  History
} from 'lucide-react';
import { motion } from 'framer-motion';
import { Button } from "@evoloop/shared/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@evoloop/shared/components/ui/card";
import { Badge } from "@evoloop/shared/components/ui/badge";
import { useProjectStore } from '@/stores/projectStore';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from '@tanstack/react-router';
import { DevicesService, LearningService, SystemService } from '@/client';
import { isLoggedIn } from '@/hooks/useAuth';

interface ChatWelcomeProps {
  // onStarterClick removed as prompts are replaced by nav
}

export const ChatWelcome: React.FC<ChatWelcomeProps> = () => {
  const { t } = useTranslation();
  const { currentProject } = useProjectStore();
  const navigate = useNavigate();

  // Fetch Devices Status (only when logged in)
  const { data: devices } = useQuery({
    queryKey: ['devices'],
    queryFn: () => DevicesService.getDevices(),
    refetchInterval: 10000,
    enabled: isLoggedIn(),
  });

  // Fetch Skills Stats (only when logged in)
  const { data: skills } = useQuery({
    queryKey: ['learnedSkills'],
    queryFn: () => LearningService.listSkills({ pageSize: 4 }),
    enabled: isLoggedIn(),
  });

  // Fetch System Status (only when logged in)
  const { data: systemStatus } = useQuery({
    queryKey: ['systemStatus'],
    queryFn: () => SystemService.getSystemStatus(),
    refetchInterval: 5000,
    enabled: isLoggedIn(),
  });

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: { y: 0, opacity: 1 }
  };

  return (
    <motion.div 
      className="flex flex-col items-center justify-center min-h-[500px] py-10 px-4 max-w-5xl mx-auto"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      {/* Hero Section */}
      <motion.div className="text-center mb-8" variants={itemVariants}>
        <div className="inline-flex items-center justify-center p-2.5 mb-5 rounded-xl bg-primary/5 border border-primary/10 shadow-sm">
          <Bot size={32} className="text-primary/60" />
        </div>
        <h1 className="text-2xl md:text-3xl font-bold tracking-tight mb-3 bg-clip-text text-transparent bg-gradient-to-b from-foreground via-foreground/90 to-foreground/50">
          {currentProject?.id !== 0 
            ? t('chat.welcome.projectReady', { name: currentProject?.name }) 
            : t('chat.welcome.globalReady')}
        </h1>
        <p className="text-muted-foreground/70 text-base max-w-xl mx-auto">
          {t('chat.welcome.subtitle')}
        </p>
      </motion.div>

      {/* Main Command Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mb-12">
        {/* System Awareness Widget */}
        <motion.div variants={itemVariants}>
          <Card className="h-full bg-muted/20 border-primary/5 hover:border-primary/10 transition-all group overflow-hidden relative">
             <div className="absolute top-0 right-0 p-4 opacity-[0.02] group-hover:opacity-[0.05] transition-opacity">
                <Cpu size={70} />
             </div>
             <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground/80">
                  <Activity size={14} className="text-muted-foreground/60" />
                  {t('chat.welcome.systemAwareness')}
                </CardTitle>
             </CardHeader>
             <CardContent className="space-y-4">
                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] uppercase tracking-wider text-muted-foreground/60">
                    <span>{t('chat.welcome.health')}</span>
                    <span className="font-bold">{systemStatus?.status === 'ok' ? '98%' : '--'}</span>
                  </div>
                  <div className="h-1 w-full bg-muted/50 rounded-full overflow-hidden">
                    <motion.div 
                      className="h-full bg-primary/40" 
                      initial={{ width: 0 }} 
                      animate={{ width: systemStatus?.status === 'ok' ? '98%' : '0%' }} 
                      transition={{ duration: 1, delay: 0.5 }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 pt-2">
                  <div className="p-2 rounded-lg bg-background/50 border border-border/50">
                    <div className="text-[10px] text-muted-foreground">{t('common.cpu')}</div>
                    <div className="text-sm font-semibold">{systemStatus ? `${Math.round(systemStatus.cpu_percent)}%` : '--'}</div>
                  </div>
                  <div className="p-2 rounded-lg bg-background/50 border border-border/50">
                    <div className="text-[10px] text-muted-foreground">{t('common.ram')}</div>
                    <div className="text-sm font-semibold">{systemStatus ? `${systemStatus.ram_used_gb} / ${systemStatus.ram_total_gb}GB` : '--'}</div>
                  </div>
                </div>
                <div className="pt-2">
                   <div className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">{t('chat.welcome.topApps')}</div>
                   <div className="flex gap-2 opacity-60 grayscale hover:grayscale-0 hover:opacity-100 transition-all">
                      <div className="w-6 h-6 rounded bg-muted/80 flex items-center justify-center p-1" title="VS Code"><LayoutGrid size={12} /></div>
                      <div className="w-6 h-6 rounded bg-muted/80 flex items-center justify-center p-1" title="Terminal"><Zap size={12} /></div>
                      <div className="w-6 h-6 rounded bg-muted/80 flex items-center justify-center p-1" title="Memory"><Brain size={12} /></div>
                   </div>
                </div>
             </CardContent>
          </Card>
        </motion.div>

        {/* Device Bridge Widget */}
        <motion.div variants={itemVariants}>
          <Card className="h-full bg-muted/20 border-primary/5 hover:border-primary/10 transition-all group overflow-hidden relative">
             <div className="absolute top-0 right-0 p-4 opacity-[0.02] group-hover:opacity-[0.05] transition-opacity">
                <Smartphone size={70} />
             </div>
             <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground/80">
                  <Dna size={14} className="text-muted-foreground/60" />
                  {t('chat.welcome.deviceBridge')}
                </CardTitle>
             </CardHeader>
              <CardContent className="flex flex-col items-center justify-center pt-4 pb-6 space-y-4">
                {devices && (devices as any).length > 0 ? (
                  (() => {
                    const primaryDevice = (devices as any)[0];
                    return (
                      <>
                        <div className="relative">
                          <div className={`w-16 h-24 rounded-xl border-2 ${primaryDevice.status === 'online' ? 'border-primary/30' : 'border-muted/30'} flex flex-col items-center justify-center bg-background/80 shadow-lg group-hover:border-primary/60 transition-colors`}>
                            <Smartphone size={32} className={primaryDevice.status === 'online' ? 'text-primary/70' : 'text-muted-foreground/40'} />
                            {primaryDevice.status === 'online' && (
                              <div className="absolute -top-1 -right-1 w-3 h-3 bg-emerald-500 rounded-full border-2 border-background animate-pulse" />
                            )}
                          </div>
                        </div>
                        <div className="text-center">
                           <div className="text-sm font-bold truncate max-w-[120px]">{primaryDevice.model || 'Unknown Device'}</div>
                           <div className="text-[10px] text-muted-foreground uppercase">
                              {primaryDevice.connection_type === 'adb' 
                                ? t('chat.welcome.connectedViaAdb') 
                                : t('chat.welcome.cloudSynced')}
                           </div>
                        </div>
                      </>
                    );
                  })()
                ) : (
                  <div className="text-center py-4 opacity-40">
                    <Smartphone size={48} className="mx-auto mb-2 opacity-20" />
                    <p className="text-xs">{t('chat.welcome.noDevices')}</p>
                  </div>
                )}
                <Button variant="ghost" size="sm" className="w-full text-[10px] border border-dashed border-border hover:bg-background h-8">
                  {t('chat.welcome.syncDevice')}
                </Button>
             </CardContent>
          </Card>
        </motion.div>

        {/* Skill Evolution Widget */}
        <motion.div variants={itemVariants}>
          <Card className="h-full bg-muted/20 border-primary/5 hover:border-primary/10 transition-all group overflow-hidden relative">
             <div className="absolute top-0 right-0 p-4 opacity-[0.02] group-hover:opacity-[0.05] transition-opacity">
                <Wand2 size={70} />
             </div>
             <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground/80">
                  <History size={14} className="text-muted-foreground/60" />
                  {t('chat.welcome.skillEvolution')}
                </CardTitle>
             </CardHeader>
             <CardContent className="space-y-3">
                <div className="space-y-2">
                   <div className="flex items-center justify-between p-2 rounded-lg bg-background/50 border border-border/50 hover:bg-background transition-colors cursor-pointer group/skill">
                    <div className="flex items-center gap-2 overflow-hidden">
                       <div className="p-1 rounded bg-muted text-muted-foreground/60"><Wand2 size={12} /></div>
                       <div className="truncate text-xs font-medium text-muted-foreground/80">File Organizer</div>
                    </div>
                    <Badge variant="outline" className="text-[9px] px-1 h-4 border-primary/20 text-muted-foreground/60">v2.1</Badge>
                  </div>
                  <div className="flex items-center justify-between p-2 rounded-lg bg-background/50 border border-border/50 hover:bg-background transition-colors cursor-pointer group/skill">
                    <div className="flex items-center gap-2 overflow-hidden">
                       <div className="p-1 rounded bg-muted text-muted-foreground/60"><Search size={12} /></div>
                       <div className="truncate text-xs font-medium text-muted-foreground/80">Web Researcher</div>
                    </div>
                    <Badge variant="outline" className="text-[9px] px-1 h-4 border-primary/20 text-muted-foreground/60">v1.4</Badge>
                  </div>
                </div>
                   <div className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">
                      {t('chat.welcome.totalSkills', { count: (skills as any)?.total || 0 })}
                   </div>
                <Button 
                  className="w-full h-8 text-[11px] font-bold" 
                  size="sm"
                  onClick={() => navigate({ to: '/learning' })}
                >
                  <PlusCircle size={14} className="mr-2" />
                  {t('chat.welcome.teachMe')}
                </Button>
             </CardContent>
          </Card>
        </motion.div>
      </div>

      {/* Navigation Grid */}
      <motion.div variants={itemVariants} className="w-full">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 w-full">
          <div 
            onClick={() => navigate({ to: '/projects' })}
            className="group cursor-pointer p-4 rounded-xl bg-background/50 border border-border/50 hover:border-primary/30 transition-all flex flex-col gap-3"
          >
            <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center text-muted-foreground group-hover:text-primary group-hover:bg-primary/5 transition-all">
              <LayoutGrid size={18} />
            </div>
            <div>
              <h3 className="text-xs font-bold mb-1">{t("chat.welcome.nav.projects")}</h3>
              <p className="text-[10px] text-muted-foreground/80 leading-relaxed">{t("chat.welcome.nav.projectsDesc")}</p>
            </div>
            <ArrowRight size={12} className="self-end text-muted-foreground/40 group-hover:text-primary transition-colors" />
          </div>

          <div 
            onClick={() => navigate({ to: '/todos' })}
            className="group cursor-pointer p-4 rounded-xl bg-background/50 border border-border/50 hover:border-primary/30 transition-all flex flex-col gap-3"
          >
            <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center text-muted-foreground group-hover:text-emerald-500 group-hover:bg-emerald-500/5 transition-all">
              <ListTodo size={18} />
            </div>
            <div>
              <h3 className="text-xs font-bold mb-1">{t("chat.welcome.nav.todos")}</h3>
              <p className="text-[10px] text-muted-foreground/80 leading-relaxed">{t("chat.welcome.nav.todosDesc")}</p>
            </div>
            <ArrowRight size={12} className="self-end text-muted-foreground/40 group-hover:text-primary transition-colors" />
          </div>

          <div 
            onClick={() => navigate({ to: '/knowledge' })}
            className="group cursor-pointer p-4 rounded-xl bg-background/50 border border-border/50 hover:border-primary/30 transition-all flex flex-col gap-3"
          >
            <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center text-muted-foreground group-hover:text-amber-500 group-hover:bg-amber-500/5 transition-all">
              <Brain size={18} />
            </div>
            <div>
              <h3 className="text-xs font-bold mb-1">{t("chat.welcome.nav.knowledge")}</h3>
              <p className="text-[10px] text-muted-foreground/80 leading-relaxed">{t("chat.welcome.nav.knowledgeDesc")}</p>
            </div>
            <ArrowRight size={12} className="self-end text-muted-foreground/40 group-hover:text-primary transition-colors" />
          </div>

          <div 
            onClick={() => navigate({ to: '/learning' })}
            className="group cursor-pointer p-4 rounded-xl bg-background/50 border border-border/50 hover:border-primary/30 transition-all flex flex-col gap-3"
          >
            <div className="w-9 h-9 rounded-lg bg-muted flex items-center justify-center text-muted-foreground group-hover:text-purple-500 group-hover:bg-purple-500/5 transition-all">
              <Wand2 size={18} />
            </div>
            <div>
              <h3 className="text-xs font-bold mb-1">{t("chat.welcome.nav.skills")}</h3>
              <p className="text-[10px] text-muted-foreground/80 leading-relaxed">{t("chat.welcome.nav.skillsDesc")}</p>
            </div>
            <ArrowRight size={12} className="self-end text-muted-foreground/40 group-hover:text-primary transition-colors" />
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
};
