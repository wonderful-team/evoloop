import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import { FileDiff } from "lucide-react"
import { useTranslation } from "react-i18next"

interface DiffDrawerProps {
    isOpen: boolean
    onClose: () => void
    path: string | null
    diff: string | null
}

export function DiffDrawer({ isOpen, onClose, path, diff }: DiffDrawerProps) {
    const { t } = useTranslation()
    if (!path || !diff) return null

    return (
        <Sheet open={isOpen} onOpenChange={(open) => !open && onClose()}>
            <SheetContent side="right" className="sm:max-w-[70vw] p-0 flex flex-col gap-0 border-l border-border shadow-2xl">
                <SheetHeader className="p-4 border-b border-border bg-muted/20 shrink-0">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-primary/10 rounded-md">
                            <FileDiff className="h-5 w-5 text-primary" />
                        </div>
                        <div className="flex flex-col min-w-0">
                            <SheetTitle className="text-sm font-semibold truncate leading-none">
                                {path.split('/').pop()}
                            </SheetTitle>
                            <span className="text-[10px] text-muted-foreground font-mono mt-1 opacity-70 truncate">
                                {path}
                            </span>
                        </div>
                    </div>
                </SheetHeader>

                <ScrollArea className="flex-1 bg-[#1e1e1e]">
                    <div className="min-w-fit">
                        <SyntaxHighlighter
                            language="diff"
                            style={vscDarkPlus as any}
                            customStyle={{
                                margin: 0,
                                padding: '20px',
                                fontSize: '13px',
                                lineHeight: '1.6',
                                background: 'transparent'
                            }}
                            showLineNumbers={false}
                        >
                            {diff}
                        </SyntaxHighlighter>
                    </div>
                </ScrollArea>

                <div className="p-3 border-t border-border bg-muted/10 text-[10px] text-muted-foreground text-center shrink-0 italic">
                    {t("chat.diff.tip")}
                </div>
            </SheetContent>
        </Sheet>
    )
}
