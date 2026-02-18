import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogDescription
} from '@evoloop/shared/components/ui/dialog'
import { Button } from '@evoloop/shared/components/ui/button'
import { Input } from '@evoloop/shared/components/ui/input'
import { Label } from '@evoloop/shared/components/ui/label'
import { FolderDown, Loader2, CheckCircle2, AlertCircle, Info } from 'lucide-react'
import { LearningService } from '@/client/sdk.gen'
import { toast } from 'sonner'
import { Card } from '@evoloop/shared/components/ui/card'

interface ImportSkillsDialogProps {
    isOpen: boolean
    onClose: () => void
    onSuccess?: () => void
}

export function ImportSkillsDialog({ isOpen, onClose, onSuccess }: ImportSkillsDialogProps) {
    const { t } = useTranslation()
    const [directory, setDirectory] = useState('skills/skills')
    const [isImporting, setIsImporting] = useState(false)
    const [result, setResult] = useState<{
        total_found: number
        imported: number
        skipped: number
        errors: string[]
    } | null>(null)

    const handleImport = async () => {
        setIsImporting(true)
        setResult(null)
        try {
            const response = await LearningService.importSkills({
                requestBody: { directory }
            })

            if (response.success) {
                setResult(response.results)
                toast.success(t('learning.import.success', 'Skills imported successfully!'))
                onSuccess?.()
            } else {
                toast.error(t('learning.import.failed', 'Failed to import skills'))
            }
        } catch (error: any) {
            console.error('Skill import failed:', error)
            toast.error(error.message || t('learning.import.error', 'An error occurred during import'))
        } finally {
            setIsImporting(false)
        }
    }

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <FolderDown className="h-5 w-5 text-primary" />
                        {t('learning.import.title', 'Import External Skills')}
                    </DialogTitle>
                    <DialogDescription>
                        {t('learning.import.description', 'Bulk import standard skills from a directory containing SKILL.md packages.')}
                    </DialogDescription>
                </DialogHeader>

                {!result ? (
                    <div className="py-6 space-y-4">
                        <div className="space-y-2">
                            <Label htmlFor="directory">{t('learning.import.directoryLabel', 'Directory Path')}</Label>
                            <Input
                                id="directory"
                                placeholder={t('learning.import.placeholder', 'e.g. skills/skills')}
                                value={directory}
                                onChange={(e) => setDirectory(e.target.value)}
                                disabled={isImporting}
                            />
                            <p className="text-[10px] text-muted-foreground flex items-center gap-1">
                                <Info className="h-3 w-3" />
                                {t('learning.import.directoryHint', 'Path relative to project root or absolute path.')}
                            </p>
                        </div>
                    </div>
                ) : (
                    <div className="py-4 space-y-4">
                        <Card className="p-4 bg-muted/30 border-dashed">
                            <div className="grid grid-cols-3 gap-2 text-center">
                                <div className="space-y-1">
                                    <div className="text-2xl font-bold">{result.total_found}</div>
                                    <div className="text-[10px] uppercase text-muted-foreground font-semibold">
                                        {t('learning.import.stats.found', 'Found')}
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <div className="text-2xl font-bold text-emerald-500">{result.imported}</div>
                                    <div className="text-[10px] uppercase text-muted-foreground font-semibold">
                                        {t('learning.import.stats.imported', 'Imported')}
                                    </div>
                                </div>
                                <div className="space-y-1">
                                    <div className="text-2xl font-bold text-orange-400">{result.skipped}</div>
                                    <div className="text-[10px] uppercase text-muted-foreground font-semibold">
                                        {t('learning.import.stats.skipped', 'Skipped')}
                                    </div>
                                </div>
                            </div>
                        </Card>

                        {result.errors.length > 0 && (
                            <div className="space-y-2">
                                <Label className="text-[10px] uppercase font-bold text-destructive flex items-center gap-1">
                                    <AlertCircle className="h-3 w-3" /> {t('learning.import.errors', 'Errors')}
                                </Label>
                                <div className="max-height-[150px] overflow-y-auto space-y-1 pr-2">
                                    {result.errors.map((err, i) => (
                                        <div key={i} className="text-[11px] p-2 bg-destructive/5 rounded border border-destructive/10 text-destructive-foreground/80">
                                            {err}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div className="flex items-center gap-2 p-3 bg-emerald-500/5 rounded-xl border border-emerald-500/20 text-emerald-600">
                            <CheckCircle2 className="h-4 w-4" />
                            <span className="text-xs font-medium">{t('learning.import.complete', 'Import process finished.')}</span>
                        </div>
                    </div>
                )}

                <DialogFooter>
                    {result ? (
                        <Button onClick={onClose} className="w-full">
                            {t('common.done', 'Done')}
                        </Button>
                    ) : (
                        <>
                            <Button variant="ghost" onClick={onClose} disabled={isImporting}>
                                {t('common.cancel', 'Cancel')}
                            </Button>
                            <Button
                                onClick={handleImport}
                                disabled={isImporting || !directory}
                                className="gap-2"
                            >
                                {isImporting && <Loader2 className="h-4 w-4 animate-spin" />}
                                {t('learning.import.button', 'Start Import')}
                            </Button>
                        </>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
