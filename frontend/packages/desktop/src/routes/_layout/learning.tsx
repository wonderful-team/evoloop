import { useEffect } from "react"
import { createFileRoute, Outlet, useRouterState, redirect } from "@tanstack/react-router"
import { isLoggedIn } from "@/hooks/useAuth"
import { AndroidMirrorConsole } from "@/components/Learning/AndroidMirrorConsole"
import { SkillLibraryView } from "@/components/Learning/SkillLibraryView"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { BookOpen, GraduationCap, Sparkles, Server, Square } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useState } from "react"
import { McpView } from "@/components/Learning/McpView"
import { RecordingButton } from "@/components/Chat/RecordingButton"
import { useRecordingStore } from "@/stores/recordingStore"
import { MultimodalSynthesizeDialog } from "@/components/Learning/MultimodalSynthesizeDialog"
import { isTauri } from "@/lib/tauri"

export const Route = createFileRoute("/_layout/learning")({
    component: LearningPage,
    beforeLoad: async () => {
        if (!isLoggedIn()) {
            throw redirect({ to: "/login" })
        }
    },
})

function LearningPage() {
    const { t } = useTranslation()
    const router = useRouterState()
    const [activeTab, setActiveTab] = useState("library")
    const [highlightSkillId, setHighlightSkillId] = useState<number | null>(null)

    const {
        sessionId,
        videoPath,
        postRecordingAction,
        setPostRecordingAction,
        isRecording,
        isPreparing,
        countdown,
        stopRecording,
        recordingSource,
        openMarkerOverlay,
        closeMarkerOverlay,
    } = useRecordingStore()
    const [synthesizeDialogOpen, setSynthesizeDialogOpen] = useState(false)
    const [isStoppingRecording, setIsStoppingRecording] = useState(false)

    // Check if we're on a child route (e.g. /learning/skills/:id/edit)
    const isChildRoute = router.location.pathname.startsWith("/learning/") && router.location.pathname !== "/learning"

    // Automatic trigger for synthesis dialog
    useEffect(() => {
        if (postRecordingAction === 'synthesize' && sessionId && videoPath) {
            setSynthesizeDialogOpen(true)
            setIsStoppingRecording(false)
        }
    }, [postRecordingAction, sessionId, videoPath])

    // Handle recording state changes - open/close marker overlay
    useEffect(() => {
        const handleRecordingState = async () => {
            if (isRecording && recordingSource === 'desktop') {
                // Open marker overlay when global recording starts
                await openMarkerOverlay()
            } else {
                // Close marker overlay when recording stops
                await closeMarkerOverlay()
            }
        }

        handleRecordingState()

        // Cleanup on unmount
        return () => {
            closeMarkerOverlay()
        }
    }, [isRecording, recordingSource, openMarkerOverlay, closeMarkerOverlay])

    const handleSynthesizeComplete = () => {
        setSynthesizeDialogOpen(false)
        setPostRecordingAction(null)
        // Navigate to skill library to see the new skill
        setActiveTab("library")
    }

    // If on child route, render the child component (Outlet)
    if (isChildRoute) {
        return <Outlet />
    }

    return (
        <div className="flex flex-col h-full gap-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {/* Page Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-3">
                        <GraduationCap className="h-6 w-6 text-primary" />
                        <h1 className="text-2xl font-bold tracking-tight text-foreground">
                            {t("learning.centerTitle")}
                        </h1>
                    </div>
                    <p className="text-muted-foreground text-sm max-w-2xl">
                        {t("learning.centerSubtitle")}
                    </p>
                </div>

                {isTauri() && (
                    <div className="flex items-center gap-2 bg-muted/30 p-1.5 rounded-xl border border-border">
                        <span className="text-xs font-medium text-muted-foreground px-2">
                            {t("learning.quickStart")}:
                        </span>
                        <RecordingButton threadId="global" />
                    </div>
                )}
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab as any} className="w-full h-full flex flex-col overflow-hidden">
                <TabsList className="bg-muted/30 p-1 rounded-lg border border-border self-start mb-2">
                    <TabsTrigger value="library" className="rounded-md px-6 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all text-left">
                        <BookOpen className="h-3.5 w-3.5" />
                        {t("learning.tabs.library")}
                    </TabsTrigger>
                    {isTauri() && (
                        <TabsTrigger value="recording" className="rounded-md px-6 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all text-left">
                            <Sparkles className="h-3.5 w-3.5" />
                            {t("learning.tabs.recording")}
                        </TabsTrigger>
                    )}
                    <TabsTrigger value="mcp" className="rounded-md px-6 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all text-left">
                        <Server className="h-3.5 w-3.5" />
                        {t("learning.tabs.mcpServers")}
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="library" className="flex-1 mt-0 overflow-hidden outline-none">
                    <SkillLibraryView
                        threadId="global"
                        highlightSkillId={highlightSkillId}
                        onClearHighlight={() => setHighlightSkillId(null)}
                    />
                </TabsContent>

                <TabsContent value="recording" className="flex-1 mt-0 overflow-hidden outline-none">
                    <AndroidMirrorConsole onOpenEditor={(skillId) => {
                        setHighlightSkillId(skillId);
                        setActiveTab("library");
                    }} />
                </TabsContent>

                <TabsContent value="mcp" className="flex-1 mt-0 overflow-hidden outline-none">
                    <McpView />
                </TabsContent>
            </Tabs>

            {/* Synthesis dialog - using MultimodalSynthesizeDialog for skill synthesis from recordings */}
            <MultimodalSynthesizeDialog
                open={synthesizeDialogOpen}
                onOpenChange={setSynthesizeDialogOpen}
                sessionId={sessionId || ""}
                threadId="global"
                videoPath={videoPath}
                onSuccess={handleSynthesizeComplete}
                sourceType={recordingSource === 'mobile' ? 'android' : 'desktop'}
            />

            {/* Countdown Overlay - Show during preparation */}
            {isPreparing && (
                <div className="fixed inset-0 z-[100] bg-black/80 flex items-center justify-center">
                    <div className="flex flex-col items-center gap-6">
                        <div className="text-white/60 text-sm font-medium">
                            {t("learning.preparingRecording")}
                        </div>
                        <div className="text-8xl font-bold text-white animate-in zoom-in duration-300">
                            {countdown}
                        </div>
                        <button
                            onClick={() => {
                                useRecordingStore.getState().setIsPreparing(false)
                                useRecordingStore.getState().setCountdown(0)
                            }}
                            className="px-4 py-2 text-white/80 hover:text-white border border-white/30 hover:border-white/60 rounded-lg transition-colors"
                        >
                            {t("common.cancel")}
                        </button>
                    </div>
                </div>
            )}

            {/* Recording Overlay - Full screen gray overlay with stop button */}
            {isRecording && (
                <div className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center">
                    <div className="flex flex-col items-center gap-6 animate-in fade-in zoom-in duration-300">
                        {/* Recording indicator */}
                        <div className="flex items-center gap-2 text-white/90">
                            {isStoppingRecording ? (
                                <>
                                    <span className="animate-spin h-5 w-5 border-2 border-white/30 border-t-white rounded-full" />
                                    <span className="text-lg font-medium tracking-wide">
                                        {t("learning.finalizingRecording")}
                                    </span>
                                </>
                            ) : (
                                <>
                                    <span className="relative flex h-4 w-4">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                                        <span className="relative inline-flex rounded-full h-4 w-4 bg-red-500"></span>
                                    </span>
                                    <span className="text-lg font-medium tracking-wide">
                                        {t("learning.recordingInProgress")}
                                    </span>
                                </>
                            )}
                        </div>

                        {/* Stop Button - Large and centered */}
                        <button
                            onClick={() => {
                                // Must set action BEFORE stopping, so GlobalRecorderManager knows to trigger synthesis
                                setPostRecordingAction('synthesize')
                                setIsStoppingRecording(true)
                                stopRecording()
                            }}
                            disabled={isStoppingRecording}
                            className="group relative flex items-center justify-center gap-3 px-12 py-6 bg-red-500 hover:bg-red-600 active:bg-red-700 text-white rounded-2xl shadow-2xl transition-all duration-200 hover:scale-105 active:scale-95 disabled:opacity-70 disabled:cursor-not-allowed"
                        >
                            <div className="flex items-center justify-center w-10 h-10 bg-white/20 rounded-lg">
                                {isStoppingRecording ? (
                                    <span className="animate-spin h-5 w-5 border-2 border-white/30 border-t-white rounded-full" />
                                ) : (
                                    <Square className="w-6 h-6 fill-current" />
                                )}
                            </div>
                            <span className="text-2xl font-bold">
                                {isStoppingRecording
                                    ? t("learning.processing")
                                    : t("learning.stopRecording")}
                            </span>
                        </button>

                        {/* Hint text */}
                        {!isStoppingRecording && (
                            <p className="text-white/60 text-sm">
                                {t("learning.recordingHint")}
                            </p>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}
