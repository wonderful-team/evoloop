import { open } from "@tauri-apps/plugin-dialog"
import { motion } from "framer-motion"
import { FolderOpen } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useWizard } from "../WizardContext"

export function ProjectsStep() {
    const { t } = useTranslation()
    const { data, setData, setCanProceed } = useWizard()

    // Update canProceed based on projects root
    useEffect(() => {
        setCanProceed(!!data.projectsRoot && data.projectsRoot.length > 0)
    }, [data.projectsRoot, setCanProceed])

    const handleBrowse = async () => {
        try {
            const selected = await open({
                directory: true,
                multiple: false,
            })
            if (typeof selected === "string") {
                setData({ projectsRoot: selected })
            }
        } catch (error) {
            toast.error(t("wizard.projects.browseError"))
        }
    }

    return (
        <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className="py-8 px-6 max-w-lg mx-auto"
        >
            <div className="text-center mb-8">
                <h2 className="text-2xl font-bold mb-2">{t("wizard.projects.title")}</h2>
                <p className="text-muted-foreground">{t("wizard.projects.subtitle")}</p>
            </div>

            <div className="space-y-6">
                {/* Directory Selector */}
                <div className="space-y-3">
                    <Label>{t("wizard.projects.label")}</Label>
                    <div className="flex gap-2">
                        <Input
                            value={data.projectsRoot}
                            onChange={(e) => setData({ projectsRoot: e.target.value })}
                            placeholder="/Users/yourname/Projects"
                            className="flex-1"
                        />
                        <Button variant="outline" onClick={handleBrowse}>
                            <FolderOpen className="h-4 w-4 mr-2" />
                            {t("wizard.projects.browse")}
                        </Button>
                    </div>
                </div>

                {/* Info Card */}
                <div className="bg-muted/50 rounded-lg p-4 space-y-2">
                    <h4 className="font-medium text-sm">{t("wizard.projects.infoTitle")}</h4>
                    <ul className="text-sm text-muted-foreground space-y-1">
                        <li>• {t("wizard.projects.info1")}</li>
                        <li>• {t("wizard.projects.info2")}</li>
                        <li>• {t("wizard.projects.info3")}</li>
                    </ul>
                </div>

                {/* Suggestions */}
                <div className="space-y-2">
                    <Label className="text-sm text-muted-foreground">
                        {t("wizard.projects.suggestions")}
                    </Label>
                    <div className="flex flex-wrap gap-2">
                        {["~/Projects", "~/Developer", "~/Code", "~/workspace"].map(
                            (path) => (
                                <Button
                                    key={path}
                                    variant="outline"
                                    size="sm"
                                    onClick={() => {
                                        setData({ projectsRoot: path })
                                    }}
                                    className="text-xs"
                                >
                                    {path}
                                </Button>
                            ),
                        )}
                    </div>
                </div>
            </div>
        </motion.div>
    )
}
