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
import { motion, AnimatePresence } from 'framer-motion';
import { cn } from "@evoloop/shared/lib/utils";
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
        staggerChildren: 0.08,
        delayChildren: 0.2
      }
    }
  };

  const itemVariants = {
    hidden: { y: 20, opacity: 0, scale: 0.98 },
    visible: { 
      y: 0, 
      opacity: 1, 
      scale: 1,
      transition: { type: "spring", stiffness: 100, damping: 20 }
    }
  };

  const cardHover = {
    y: -5,
    transition: { type: "spring", stiffness: 400, damping: 10 }
  };

  return (
    <motion.div 
      className="flex flex-col items-center justify-center min-h-[500px] py-10 px-4 max-w-6xl mx-auto relative"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >
      {/* Background Decorative Glows */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[120px] -z-10 animate-pulse" />
      <div className="absolute bottom-1/4 left-1/4 w-[300px] h-[300px] bg-purple-500/5 rounded-full blur-[100px] -z-10" />

      {/* Hero Section */}
      <motion.div className="text-center mb-12" variants={itemVariants}>
        <motion.div 
          className="inline-flex items-center justify-center p-3 mb-6 rounded-2xl bg-gradient-to-br from-primary/10 to-primary/5 border border-primary/20 shadow-xl shadow-primary/5"
          whileHover={{ rotate: [0, -5, 5, 0], transition: { duration: 0.5 } }}
        >
          <Bot size={40} className="text-primary" />
        </motion.div>
        <h1 className="text-3xl md:text-5xl font-bold tracking-tight mb-4 bg-clip-text text-transparent bg-gradient-to-b from-foreground via-foreground/90 to-foreground/40 pb-2">
          {currentProject?.id !== 0 
            ? t('chat.welcome.projectReady', { name: currentProject?.name }) 
            : t('chat.welcome.globalReady')}
        </h1>
        <p className="text-muted-foreground/60 text-lg max-w-2xl mx-auto leading-relaxed">
          {t('chat.welcome.subtitle')}
        </p>
      </motion.div>

      {/* Main Command Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mb-16">
        {/* System Awareness Widget */}
        <motion.div variants={itemVariants} whileHover={cardHover}>
          <Card className="h-full bg-background/40 backdrop-blur-md border-primary/10 hover:border-primary/30 transition-all group overflow-hidden relative shadow-lg">
             <div className="absolute top-0 right-0 p-4 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity">
                <Cpu size={80} />
             </div>
             <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-bold text-muted-foreground/90 tracking-tight">
                  <Activity size={16} className="text-primary/60" />
                  {t('chat.welcome.systemAwareness')}
                </CardTitle>
             </CardHeader>
             <CardContent className="space-y-5">
                <div className="space-y-2">
                  <div className="flex justify-between text-[10px] uppercase font-black tracking-widest text-muted-foreground/40">
                    <span>{t('chat.welcome.health')}</span>
                    <span className="text-emerald-500">{systemStatus?.status === 'ok' ? 'OPTIMAL' : '--'}</span>
                  </div>
                  <div className="h-1.5 w-full bg-muted/30 rounded-full overflow-hidden">
                    <motion.div 
                      className="h-full bg-gradient-to-r from-primary/60 to-primary" 
                      initial={{ width: 0 }} 
                      animate={{ width: systemStatus?.status === 'ok' ? '98%' : '0%' }} 
                      transition={{ duration: 1.5, ease: "easeOut" }}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <div className="p-3 rounded-xl bg-muted/30 border border-white/5 shadow-inner">
                    <div className="text-[10px] font-bold text-muted-foreground/50 uppercase mb-1">{t('common.cpu')}</div>
                    <div className="text-lg font-black tracking-tighter">{systemStatus ? `${Math.round(systemStatus.cpu_percent)}%` : '--'}</div>
                  </div>
                  <div className="p-3 rounded-xl bg-muted/30 border border-white/5 shadow-inner">
                    <div className="text-[10px] font-bold text-muted-foreground/50 uppercase mb-1">{t('common.ram')}</div>
                    <div className="text-lg font-black tracking-tighter">{systemStatus ? `${systemStatus.ram_used_gb}G` : '--'}</div>
                  </div>
                </div>
             </CardContent>
          </Card>
        </motion.div>

        {/* Device Bridge Widget */}
        <motion.div variants={itemVariants} whileHover={cardHover}>
          <Card className="h-full bg-background/40 backdrop-blur-md border-primary/10 hover:border-primary/30 transition-all group overflow-hidden relative shadow-lg">
             <div className="absolute top-0 right-0 p-4 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity">
                <Smartphone size={80} />
             </div>
             <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-bold text-muted-foreground/90 tracking-tight">
                  <Dna size={16} className="text-primary/60" />
                  {t('chat.welcome.deviceBridge')}
                </CardTitle>
             </CardHeader>
              <CardContent className="flex flex-col items-center justify-center pt-2 pb-6 space-y-5">
                {devices && (devices as any).length > 0 ? (
                  (() => {
                    const primaryDevice = (devices as any)[0];
                    return (
                      <>
                        <div className="relative pt-2">
                          <div className={`w-16 h-24 rounded-2xl border-2 ${primaryDevice.status === 'online' ? 'border-primary/40' : 'border-muted/30'} flex flex-col items-center justify-center bg-muted/20 shadow-2xl group-hover:border-primary transition-colors`}>
                            <Smartphone size={32} className={primaryDevice.status === 'online' ? 'text-primary' : 'text-muted-foreground/40'} />
                            {primaryDevice.status === 'online' && (
                              <div className="absolute -top-1 -right-1 w-4 h-4 bg-emerald-500 rounded-full border-2 border-background shadow-lg animate-pulse" />
                            )}
                          </div>
                        </div>
                        <div className="text-center">
                           <div className="text-sm font-black truncate max-w-[140px] uppercase tracking-tight">{primaryDevice.model || 'Unknown'}</div>
                           <div className="text-[9px] font-bold text-muted-foreground/50 uppercase tracking-widest mt-1">
                              {primaryDevice.connection_type === 'adb' 
                                ? t('chat.welcome.connectedViaAdb') 
                                : t('chat.welcome.cloudSynced')}
                           </div>
                        </div>
                      </>
                    );
                  })()
                ) : (
                  <div className="text-center py-6 opacity-40">
                    <Smartphone size={48} className="mx-auto mb-2 opacity-10" />
                    <p className="text-[10px] font-bold uppercase tracking-widest">{t('chat.welcome.noDevices')}</p>
                  </div>
                )}
                <Button variant="ghost" size="sm" className="w-full text-[10px] font-bold border border-dashed border-primary/20 hover:bg-primary/5 h-9 rounded-xl">
                  {t('chat.welcome.syncDevice')}
                </Button>
             </CardContent>
          </Card>
        </motion.div>

        {/* Skill Evolution Widget */}
        <motion.div variants={itemVariants} whileHover={cardHover}>
          <Card className="h-full bg-background/40 backdrop-blur-md border-primary/10 hover:border-primary/30 transition-all group overflow-hidden relative shadow-lg">
             <div className="absolute top-0 right-0 p-4 opacity-[0.03] group-hover:opacity-[0.08] transition-opacity">
                <Wand2 size={80} />
             </div>
             <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-2 text-sm font-bold text-muted-foreground/90 tracking-tight">
                  <History size={16} className="text-primary/60" />
                  {t('chat.welcome.skillEvolution')}
                </CardTitle>
             </CardHeader>
             <CardContent className="space-y-4">
                <div className="space-y-2">
                   <div className="flex items-center justify-between p-2.5 rounded-xl bg-muted/30 border border-white/5 hover:bg-muted/50 transition-all cursor-pointer group/skill">
                    <div className="flex items-center gap-2 overflow-hidden">
                       <div className="p-1.5 rounded-lg bg-background text-primary/60 shadow-sm"><Wand2 size={12} /></div>
                       <div className="truncate text-xs font-bold text-muted-foreground/80">File Organizer</div>
                    </div>
                    <Badge variant="outline" className="text-[9px] px-1.5 h-4 border-primary/20 bg-primary/5 text-primary/70">v2.1</Badge>
                  </div>
                  <div className="flex items-center justify-between p-2.5 rounded-xl bg-muted/30 border border-white/5 hover:bg-muted/50 transition-all cursor-pointer group/skill">
                    <div className="flex items-center gap-2 overflow-hidden">
                       <div className="p-1.5 rounded-lg bg-background text-primary/60 shadow-sm"><Search size={12} /></div>
                       <div className="truncate text-xs font-bold text-muted-foreground/80">Web Researcher</div>
                    </div>
                    <Badge variant="outline" className="text-[9px] px-1.5 h-4 border-primary/20 bg-primary/5 text-primary/70">v1.4</Badge>
                  </div>
                </div>
                <Button 
                  className="w-full h-9 text-[11px] font-black rounded-xl shadow-lg shadow-primary/20" 
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
          {[
            { to: '/projects', icon: <LayoutGrid size={20} />, label: t("chat.welcome.nav.projects"), desc: t("chat.welcome.nav.projectsDesc"), color: "text-primary" },
            { to: '/todos', icon: <ListTodo size={20} />, label: t("chat.welcome.nav.todos"), desc: t("chat.welcome.nav.todosDesc"), color: "text-emerald-500" },
            { to: '/knowledge', icon: <Brain size={20} />, label: t("chat.welcome.nav.knowledge"), desc: t("chat.welcome.nav.knowledgeDesc"), color: "text-amber-500" },
            { to: '/learning', icon: <Wand2 size={20} />, label: t("chat.welcome.nav.skills"), desc: t("chat.welcome.nav.skillsDesc"), color: "text-purple-500" }
          ].map((nav, idx) => (
            <motion.div 
              key={idx}
              whileHover={{ scale: 1.02, y: -2 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate({ to: nav.to as any })}
              className="group cursor-pointer p-5 rounded-2xl bg-background/40 backdrop-blur-sm border border-border/40 hover:border-primary/20 hover:bg-muted/20 transition-all flex flex-col gap-4 shadow-sm"
            >
              <div className={cn("w-10 h-10 rounded-xl bg-muted/50 flex items-center justify-center group-hover:scale-110 transition-transform shadow-inner", nav.color)}>
                {nav.icon}
              </div>
              <div>
                <h3 className="text-xs font-black mb-1 uppercase tracking-tight">{nav.label}</h3>
                <p className="text-[10px] text-muted-foreground/60 leading-relaxed line-clamp-2">{nav.desc}</p>
              </div>
              <div className="flex items-center justify-end">
                <div className="w-6 h-6 rounded-full bg-muted/30 flex items-center justify-center group-hover:bg-primary group-hover:text-white transition-all">
                  <ArrowRight size={12} />
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
};
