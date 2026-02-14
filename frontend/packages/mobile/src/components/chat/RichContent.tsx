import { useState } from "react"
import { useTranslation } from "react-i18next"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import remarkGfm from "remark-gfm"
import { FileText, X } from "lucide-react"
import { cn } from "@evoloop/shared"
import { Button } from "@evoloop/shared/components/ui/button"
import { Dialog, DialogContent, DialogTitle } from "@evoloop/shared/components/ui/dialog"

export function ImageViewer({
    src,
    isOpen,
    onClose,
}: {
    src: string
    isOpen: boolean
    onClose: () => void
}) {
    const { t } = useTranslation()
    if (!isOpen) return null
    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-full h-full p-0 bg-black/90 border-none sm:rounded-none flex flex-col justify-center items-center">
                <DialogTitle className="sr-only">
                    {t("chat.messageList.imageViewer")}
                </DialogTitle>
                <div className="relative w-full h-full flex items-center justify-center p-2">
                    <img
                        src={src}
                        alt="Full view"
                        className="max-w-full max-h-full object-contain"
                    />
                    <Button
                        variant="ghost"
                        size="icon"
                        className="absolute top-4 right-4 text-white/70 hover:text-white hover:bg-white/20 rounded-full"
                        onClick={onClose}
                    >
                        <X className="w-6 h-6" />
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    )
}

export function RichContent({ content, className }: { content: any; className?: string }) {
    const { t } = useTranslation()
    const [viewerImage, setViewerImage] = useState<string | null>(null)

    if (typeof content !== "string") {
        let displayContent = ""
        try {
            // Check if it's a chat command payload
            if (content && content.command_type === "chat" && content.params?.message) {
                displayContent = content.params.message
                // Add attachments info if any
                if (content.params.attachments?.length > 0) {
                    const atts = (content.params.attachments as any[]).map(a => `[${a.type}]`).join(" ")
                    displayContent = atts + "\n" + displayContent
                }
            } else {
                displayContent = JSON.stringify(content, null, 2)
            }
        } catch (e) {
            displayContent = String(content)
        }

        return (
            <div className={cn("whitespace-pre-wrap", className)}>
                {displayContent}
            </div>
        )
    }

    // Split by [Image: ...] or [File: ...]
    const parts = content.split(/(\[(?:Image|File):\s*https?:\/\/[^\]]+\])/g)

    const handleFileClick = (url: string) => {
        window.open(url, "_blank")
    }

    return (
        <div className={cn("text-sm leading-relaxed overflow-hidden", className)}>
            {parts.map((part, index) => {
                const imageMatch = part.match(/^\[Image:\s*(https?:\/\/[^\]]+)\]$/)
                const fileMatch = part.match(/^\[File:\s*(https?:\/\/[^\]]+)\]$/)

                if (imageMatch) {
                    const url = imageMatch[1]
                    return (
                        <div key={index} className="my-2">
                            <img
                                src={url}
                                alt="User upload"
                                className="max-w-[200px] max-h-[200px] rounded-lg border bg-muted object-cover cursor-zoom-in hover:brightness-90 transition-all"
                                onClick={() => setViewerImage(url)}
                            />
                        </div>
                    )
                }

                if (fileMatch) {
                    const url = fileMatch[1]
                    const filename = url.split("/").pop() || "File"
                    return (
                        <div
                            key={index}
                            className="my-2 inline-flex items-center gap-2 p-3 bg-muted/50 border rounded-lg cursor-pointer hover:bg-muted transition-colors max-w-full"
                            onClick={() => handleFileClick(url)}
                        >
                            <div className="bg-primary/10 p-2 rounded-md">
                                <FileText className="w-5 h-5 text-primary" />
                            </div>
                            <div className="flex flex-col overflow-hidden">
                                <span className="text-sm font-medium truncate">
                                    {decodeURIComponent(filename)}
                                </span>
                                <span className="text-xs text-muted-foreground uppercase">
                                    {t("chat.messageList.clickToOpen")}
                                </span>
                            </div>
                        </div>
                    )
                }

                if (!part) return null

                return (
                    <ReactMarkdown
                        key={index}
                        remarkPlugins={[remarkGfm]}
                        components={{
                            code({ node, inline, className, children, ...props }: any) {
                                const match = /language-(\w+)/.exec(className || "")
                                return !inline && match ? (
                                    <div className="my-2 rounded-md overflow-hidden bg-[#1e1e1e]">
                                        <div className="flex items-center justify-between px-3 py-1 bg-[#252526] text-[10px] text-gray-400 border-b border-[#3e3e3e]">
                                            <span>{match[1]}</span>
                                            <button
                                                onClick={() =>
                                                    navigator.clipboard.writeText(String(children))
                                                }
                                                className="hover:text-white transition-colors"
                                            >
                                                {t("chat.messageList.copy")}
                                            </button>
                                        </div>
                                        <SyntaxHighlighter
                                            style={vscDarkPlus as any}
                                            language={match[1]}
                                            PreTag="div"
                                            customStyle={{
                                                margin: 0,
                                                borderRadius: 0,
                                                fontSize: "12px",
                                            }}
                                            {...props}
                                        >
                                            {String(children).replace(/\n$/, "")}
                                        </SyntaxHighlighter>
                                    </div>
                                ) : (
                                    <code
                                        className="bg-muted px-1.5 py-0.5 rounded text-[85%] font-mono"
                                        {...props}
                                    >
                                        {children}
                                    </code>
                                )
                            },
                            p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                            ul: ({ children }) => (
                                <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>
                            ),
                            ol: ({ children }) => (
                                <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>
                            ),
                            a: ({ href, children }) => (
                                <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-primary underline underline-offset-4 hover:opacity-80 break-all"
                                >
                                    {children}
                                </a>
                            ),
                            blockquote: ({ children }) => (
                                <blockquote className="border-l-4 border-primary/30 pl-3 italic text-muted-foreground my-2">
                                    {children}
                                </blockquote>
                            ),
                            table: ({ children }) => (
                                <div className="overflow-x-auto my-2 rounded-lg border">
                                    <table className="w-full text-sm text-left">{children}</table>
                                </div>
                            ),
                            th: ({ children }) => (
                                <th className="bg-muted px-4 py-2 font-medium border-b">
                                    {children}
                                </th>
                            ),
                            td: ({ children }) => (
                                <td className="px-4 py-2 border-b last:border-0">{children}</td>
                            ),
                            img: ({ src, alt }) => (
                                <img
                                    src={src}
                                    alt={alt}
                                    className="max-w-full rounded-lg my-2"
                                />
                            ),
                        }}
                    >
                        {part}
                    </ReactMarkdown>
                )
            })
            }

            <ImageViewer
                isOpen={!!viewerImage}
                src={viewerImage || ""}
                onClose={() => setViewerImage(null)}
            />
        </div>
    )
}
