import { useState } from "react"
import { useTranslation } from "react-i18next"
import {
    AlertDialog,
    AlertDialogAction,
    AlertDialogCancel,
    AlertDialogContent,
    AlertDialogDescription,
    AlertDialogFooter,
    AlertDialogHeader,
    AlertDialogTitle,
} from "@evoloop/shared/components/ui/alert-dialog"
import { Checkbox } from "@evoloop/shared/components/ui/checkbox"
import { Label } from "@evoloop/shared/components/ui/label"


interface RewindConfirmDialogProps {
    open: boolean
    onOpenChange: (open: boolean) => void
    onConfirm: (revertFiles: boolean) => void
    mode?: "rewind" | "retry"
}

export function RewindConfirmDialog({
    open,
    onOpenChange,
    onConfirm,
    mode = "rewind",
}: RewindConfirmDialogProps) {
    const { t } = useTranslation()
    const [revertFiles, setRevertFiles] = useState(true)

    const title = mode === "rewind"
        ? t("chat.rewind.confirmTitle", "确认撤回")
        : t("chat.retry.confirmTitle", "确认重试")

    const description = mode === "rewind"
        ? t("chat.rewind.confirmDescription", "将删除此消息及其后的所有内容。")
        : t("chat.retry.confirmDescription", "将删除后续内容并重新尝试。")

    return (
        <AlertDialog open={open} onOpenChange={onOpenChange}>
            <AlertDialogContent>
                <AlertDialogHeader>
                    <AlertDialogTitle>{title}</AlertDialogTitle>
                    <AlertDialogDescription>{description}</AlertDialogDescription>
                </AlertDialogHeader>

                <div className="flex items-center gap-3 py-4">
                    <Checkbox
                        id="revert-files"
                        checked={revertFiles}
                        onCheckedChange={(checked) => setRevertFiles(checked === true)}
                    />
                    <Label htmlFor="revert-files" className="text-sm cursor-pointer">
                        {t("chat.rewind.revertFiles", "同时恢复 Agent 修改过的文件内容")}
                        <span className="block text-xs text-muted-foreground">
                            {t("chat.rewind.revertFilesHint", "（恢复到修改前的状态）")}
                        </span>
                    </Label>
                </div>

                <AlertDialogFooter>
                    <AlertDialogCancel>
                        {t("common.cancel", "取消")}
                    </AlertDialogCancel>
                    <AlertDialogAction onClick={() => onConfirm(revertFiles)}>
                        {mode === "rewind" ? t("chat.rewind.confirm", "确认撤回") : t("chat.retry.confirm", "确认重试")}
                    </AlertDialogAction>
                </AlertDialogFooter>
            </AlertDialogContent>
        </AlertDialog>
    )
}
