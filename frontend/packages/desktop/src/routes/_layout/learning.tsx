import { createFileRoute } from "@tanstack/react-router"
import { AndroidMirrorConsole } from "@/components/Learning/AndroidMirrorConsole"
import { SkillLibraryView } from "@/components/Learning/SkillLibraryView"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@evoloop/shared/components/ui/tabs"
import { BookOpen, GraduationCap, Sparkles, Server } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useState } from "react"
import { McpView } from "@/components/Learning/McpView"

export const Route = createFileRoute("/_layout/learning")({
    component: LearningPage,
})

function LearningPage() {
    const { t } = useTranslation()
    const [activeTab, setActiveTab] = useState("library")
    const [highlightSkillId, setHighlightSkillId] = useState<number | null>(null)

    return (
        <div className="flex flex-col h-full gap-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {/* Page Header */}
            <div className="flex flex-col gap-1">
                <div className="flex items-center gap-3">
                    <GraduationCap className="h-6 w-6 text-primary" />
                    <h1 className="text-2xl font-bold tracking-tight text-foreground">
                        {t("learning.centerTitle", "Learning Center")}
                    </h1>
                </div>
                <p className="text-muted-foreground text-sm max-w-2xl">
                    {t("learning.centerSubtitle", "Manage your learned skills and train the agent through interactive recording sessions.")}
                </p>
            </div>

            <Tabs value={activeTab} onValueChange={setActiveTab as any} className="w-full h-full flex flex-col">
                <TabsList className="bg-muted/30 p-1 rounded-lg border self-start mb-2">
                    <TabsTrigger value="library" className="rounded-md px-6 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all">
                        <BookOpen className="h-3.5 w-3.5" />
                        {t("learning.tabs.library", "Skill Library")}
                    </TabsTrigger>
                    <TabsTrigger value="recording" className="rounded-md px-6 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all">
                        <Sparkles className="h-3.5 w-3.5" />
                        {t("learning.tabs.recording", "Active Recording")}
                    </TabsTrigger>
                    <TabsTrigger value="mcp" className="rounded-md px-6 gap-2 text-xs data-[state=active]:bg-background data-[state=active]:shadow-sm transition-all">
                        <Server className="h-3.5 w-3.5" />
                        {t("sidebar.mcpServers", "MCP Servers")}
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="library" className="flex-1 mt-0">
                    <SkillLibraryView
                        threadId="global"
                        highlightSkillId={highlightSkillId}
                        onClearHighlight={() => setHighlightSkillId(null)}
                    />
                </TabsContent>

                <TabsContent value="recording" className="flex-1 mt-0">
                    <AndroidMirrorConsole onOpenEditor={(skillId) => {
                        setHighlightSkillId(skillId);
                        setActiveTab("library");
                    }} />
                </TabsContent>

                <TabsContent value="mcp" className="flex-1 mt-0">
                    <McpView />
                </TabsContent>
            </Tabs>
        </div>
    )
}
