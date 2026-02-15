import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Smartphone, RefreshCcw, Monitor, StopCircle, AlertTriangle, CheckCircle2, Loader2, Sparkles } from 'lucide-react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { MirrorService } from '@/services/mirror';
import { Button } from '@evoloop/shared/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@evoloop/shared/components/ui/card';
import { Badge } from '@evoloop/shared/components/ui/badge';
import { toast } from 'sonner';
import { ScrollArea } from '@evoloop/shared/components/ui/scroll-area';
import { SynthesizeSkillDialog } from './SynthesizeSkillDialog';

interface AndroidMirrorConsoleProps {
    onOpenEditor?: (skillId: number) => void;
}

export function AndroidMirrorConsole({ onOpenEditor }: AndroidMirrorConsoleProps) {
    const { t } = useTranslation();
    const [activeSession, setActiveSession] = useState<{ sessionId: string, deviceId: string } | null>(null);
    const [synthesizeOpen, setSynthesizeOpen] = useState(false);
    const [lastSessionId, setLastSessionId] = useState<string | null>(null);

    const { data, isLoading, refetch, isFetching } = useQuery({
        queryKey: ['mirror-devices'],
        queryFn: () => MirrorService.listDevices(),
        refetchInterval: 5000,
    });

    const startMutation = useMutation({
        mutationFn: (deviceId: string) => MirrorService.startMirror(deviceId),
        onSuccess: (res) => {
            if (res.success) {
                setActiveSession({ sessionId: res.session_id, deviceId: res.device_id });
                toast.success(t('learning.mirror.active'));
            }
        },
        onError: (err: any) => {
            toast.error(err.message || "Failed to start mirror");
        }
    });

    const stopMutation = useMutation({
        mutationFn: (sessionId: string) => MirrorService.stopMirror(sessionId),
        onSuccess: (_: any, sessionId: string) => {
            setActiveSession(null);
            setLastSessionId(sessionId);
            setSynthesizeOpen(true);
            toast.info(t('learning.mirror.stop'));
        }
    });

    const devices = data?.devices || [];
    const scrcpyAvailable = data?.scrcpy_available ?? true;

    return (
        <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold tracking-tight flex items-center gap-3">
                        <Smartphone className="h-6 w-6 text-primary" />
                        {t('learning.mirror.title')}
                    </h1>
                    <p className="text-muted-foreground">{t('learning.mirror.description')}</p>
                </div>
                <Button
                    variant="outline"
                    size="icon"
                    onClick={() => refetch()}
                    disabled={isFetching}
                    className="h-9 w-9"
                >
                    <RefreshCcw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} />
                </Button>
            </div>

            {!scrcpyAvailable && (
                <div className="p-4 rounded-lg bg-destructive/10 border border-destructive/20 flex items-center gap-3 text-destructive">
                    <AlertTriangle className="h-5 w-5 shrink-0" />
                    <div>
                        <p className="text-sm font-bold">{t('learning.mirror.warning')}</p>
                        <p className="text-xs opacity-90">{t('learning.mirror.scrcpyNotInstalled')}</p>
                    </div>
                </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 space-y-4">
                    <Card className="border-none shadow-sm bg-card/50 backdrop-blur-md">
                        <CardHeader className="py-4 px-6 border-b bg-muted/30">
                            <div className="flex items-center justify-between">
                                <CardTitle className="text-sm font-bold uppercase tracking-wider text-muted-foreground/80">
                                    {t('learning.mirror.devices')}
                                </CardTitle>
                                <Badge variant="secondary" className="font-mono text-[10px]">
                                    {devices.length} {t('learning.mirror.found')}
                                </Badge>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            <ScrollArea className="h-[450px]">
                                {isLoading ? (
                                    <div className="h-[400px] flex flex-col items-center justify-center gap-3">
                                        <Loader2 className="h-8 w-8 animate-spin text-primary/30" />
                                        <p className="text-sm text-muted-foreground/50">{t('learning.mirror.connecting')}</p>
                                    </div>
                                ) : devices.length === 0 ? (
                                    <div className="h-[400px] flex flex-col items-center justify-center text-center p-8 gap-4 opacity-40">
                                        <Smartphone className="h-12 w-12 text-muted-foreground" />
                                        <p className="text-sm text-muted-foreground max-w-[200px]">
                                            {t('learning.mirror.noDevices')}
                                        </p>
                                    </div>
                                ) : (
                                    <div className="divide-y divide-border/50">
                                        {devices.map((device) => {
                                            const isMyActive = activeSession?.deviceId === device.serial;
                                            return (
                                                <div
                                                    key={device.serial}
                                                    className={`group p-4 flex items-center justify-between transition-colors hover:bg-accent/5 ${isMyActive ? 'bg-primary/5' : ''}`}
                                                >
                                                    <div className="flex items-center gap-4">
                                                        <div className={`p-2.5 rounded-xl transition-all ${isMyActive
                                                            ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20'
                                                            : 'bg-muted text-muted-foreground'
                                                            }`}>
                                                            <Smartphone className="h-5 w-5" />
                                                        </div>
                                                        <div className="space-y-0.5">
                                                            <p className="text-sm font-bold tracking-tight">{device.serial}</p>
                                                            <div className="flex items-center gap-2">
                                                                <div className={`h-1.5 w-1.5 rounded-full ${device.status === 'device' ? 'bg-green-500' : 'bg-yellow-500'}`} />
                                                                <span className="text-[10px] uppercase font-bold text-muted-foreground/60">{device.status}</span>
                                                            </div>
                                                        </div>
                                                    </div>

                                                    <div className="flex items-center gap-2">
                                                        {isMyActive ? (
                                                            <Button
                                                                size="sm"
                                                                variant="destructive"
                                                                onClick={() => stopMutation.mutate(activeSession.sessionId)}
                                                                className="h-8 rounded-lg font-bold"
                                                                disabled={stopMutation.isPending}
                                                            >
                                                                {stopMutation.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <StopCircle className="h-3 w-3 mr-1.5" />}
                                                                {t('learning.mirror.stop')}
                                                            </Button>
                                                        ) : (
                                                            <Button
                                                                size="sm"
                                                                variant="outline"
                                                                disabled={!!activeSession || device.status !== 'device' || startMutation.isPending}
                                                                onClick={() => startMutation.mutate(device.serial)}
                                                                className="h-8 rounded-lg font-bold hover:bg-primary hover:text-primary-foreground hover:border-primary transition-all"
                                                            >
                                                                {startMutation.isPending && startMutation.variables === device.serial ? (
                                                                    <Loader2 className="h-3 w-3 animate-spin" />
                                                                ) : (
                                                                    <Monitor className="h-3 w-3 mr-1.5" />
                                                                )}
                                                                {t('learning.mirror.start')}
                                                            </Button>
                                                        )}
                                                    </div>
                                                </div>
                                            );
                                        })}
                                    </div>
                                )}
                            </ScrollArea>
                        </CardContent>
                    </Card>
                </div>

                <div className="space-y-6">
                    <Card className="border-none shadow-sm bg-gradient-to-br from-primary/5 to-purple-500/5 backdrop-blur-md overflow-hidden relative group h-full flex flex-col items-center justify-center p-8 text-center border-2 border-white/5">
                        <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 blur-[60px] rounded-full -mr-16 -mt-16 pointer-events-none" />
                        <div className="absolute bottom-0 left-0 w-32 h-32 bg-purple-500/10 blur-[60px] rounded-full -ml-16 -mb-16 pointer-events-none" />

                        {activeSession ? (
                            <div className="space-y-6 animate-in zoom-in-95 duration-500">
                                <div className="relative inline-block">
                                    <div className="absolute -inset-4 bg-primary/20 rounded-full blur-2xl animate-pulse" />
                                    <div className="relative h-20 w-20 bg-background rounded-2xl flex items-center justify-center border-2 border-primary/20 shadow-xl">
                                        <Monitor className="h-10 w-10 text-primary" />
                                    </div>
                                    <div className="absolute -bottom-1 -right-1 h-6 w-6 bg-green-500 rounded-full border-4 border-background flex items-center justify-center shadow-md">
                                        <CheckCircle2 className="h-3 w-3 text-white" />
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <h4 className="font-bold text-lg">{t('learning.mirror.active')}</h4>
                                    <div className="flex flex-col items-center gap-1.5">
                                        <span className="text-[10px] font-bold text-muted-foreground/60 uppercase tracking-widest leading-none">{t('learning.mirror.deviceId')}</span>
                                        <code className="bg-black/20 px-2 py-0.5 rounded text-primary text-[10px] font-mono border border-primary/10">
                                            {activeSession.deviceId}
                                        </code>
                                    </div>
                                </div>
                                <Badge variant="outline" className="bg-primary/5 text-primary border-primary/20 px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider">
                                    {t('learning.mirror.liveOverlay')}
                                </Badge>
                            </div>
                        ) : lastSessionId ? (
                            <div className="space-y-6 animate-in fade-in duration-500 text-center">
                                <div className="relative h-20 w-20 bg-primary/10 rounded-full flex items-center justify-center mx-auto border border-primary/20">
                                    <Sparkles className="h-10 w-10 text-primary animate-pulse" />
                                </div>
                                <div className="space-y-2">
                                    <h4 className="font-bold">{t('learning.createSkill')}</h4>
                                    <p className="text-xs text-muted-foreground px-4">
                                        {t('learning.createSkillDesc')}
                                    </p>
                                </div>
                                <Button
                                    className="gap-2 font-bold"
                                    onClick={() => setSynthesizeOpen(true)}
                                >
                                    <Sparkles className="h-4 w-4" />
                                    {t('learning.synthesize')}
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => setLastSessionId(null)} className="text-[10px] text-muted-foreground uppercase tracking-widest">
                                    {t('common.cancel')}
                                </Button>
                            </div>
                        ) : (
                            <div className="space-y-6 opacity-40">
                                <div className="h-20 w-20 bg-muted/50 rounded-2xl flex items-center justify-center mx-auto border-2 border-dashed border-muted-foreground/20">
                                    <Monitor className="h-10 w-10 text-muted-foreground/50" />
                                </div>
                                <div className="space-y-3">
                                    <div className="h-1.5 w-24 bg-muted rounded-full mx-auto" />
                                    <div className="h-1 w-16 bg-muted/50 rounded-full mx-auto" />
                                </div>
                                <p className="text-xs font-medium text-muted-foreground max-w-[160px] mx-auto leading-relaxed">
                                    {t('learning.mirror.description')}
                                </p>
                            </div>
                        )}
                    </Card>
                </div>
            </div>

            <SynthesizeSkillDialog
                open={synthesizeOpen}
                onOpenChange={setSynthesizeOpen}
                sessionId={lastSessionId || ""}
                threadId="global"
                onOpenEditor={onOpenEditor}
            />
        </div>
    );
}
