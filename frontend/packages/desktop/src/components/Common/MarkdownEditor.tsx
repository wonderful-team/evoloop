/**
 * MarkdownEditor - A markdown editor with live preview
 */

import { useState, useCallback } from "react"
import { Eye, Edit3, SplitSquareHorizontal, Bold, Italic, List, Link as LinkIcon, Code, Quote } from "lucide-react"
import ReactMarkdown from "react-markdown"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"
import remarkGfm from "remark-gfm"
import { Button } from "@evoloop/shared/components/ui/button"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { cn } from "@evoloop/shared/lib/utils"
import { useTranslation } from "react-i18next"

// Markdown Preview Component
function MarkdownPreview({ content }: { content: string }) {
    const { t } = useTranslation()

    return (
        <div className="prose prose-sm max-w-none dark:prose-invert p-4 overflow-auto h-full">
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                    code({ node, inline, className, children, ...props }: any) {
                        const match = /language-(\w+)/.exec(className || "")
                        const codeString = String(children).replace(/\n$/, "")

                        if (!inline && match) {
                            return (
                                <div className="my-2 rounded-md overflow-hidden bg-[#1e1e1e]">
                                    <div className="flex items-center justify-between px-3 py-1 bg-[#252526] text-[10px] text-gray-400 border-b border-[#3e3e3e]">
                                        <span>{match[1]}</span>
                                        <button
                                            type="button"
                                            onClick={() => navigator.clipboard.writeText(codeString)}
                                            className="hover:text-white transition-colors"
                                        >
                                            {t("chat.messageList.copy", "Copy")}
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
                                        {codeString}
                                    </SyntaxHighlighter>
                                </div>
                            )
                        }

                        return (
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
                            className="text-primary underline underline-offset-4 hover:opacity-80"
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
                    h1: ({ children }) => <h1 className="text-2xl font-bold mt-6 mb-4">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-xl font-bold mt-5 mb-3">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-lg font-bold mt-4 mb-2">{children}</h3>,
                    hr: () => <hr className="my-6 border-border" />,
                }}
            >
                {content || t("learning.editor.noContent", "*No content*")}
            </ReactMarkdown>
        </div>
    )
}

interface MarkdownEditorProps {
    value: string
    onChange: (value: string) => void
    placeholder?: string
    className?: string
}

type ViewMode = "edit" | "preview" | "split"

export function MarkdownEditor({ value, onChange, placeholder, className }: MarkdownEditorProps) {
    const { t } = useTranslation()
    const [viewMode, setViewMode] = useState<ViewMode>("preview")

    const insertText = useCallback(
        (before: string, after: string = "") => {
            const textarea = document.querySelector(".markdown-textarea") as HTMLTextAreaElement
            if (!textarea) return

            const start = textarea.selectionStart
            const end = textarea.selectionEnd
            const selectedText = value.substring(start, end)
            const newText = value.substring(0, start) + before + selectedText + after + value.substring(end)

            onChange(newText)

            // Restore focus and selection
            setTimeout(() => {
                textarea.focus()
                const newCursorPos = start + before.length + selectedText.length
                textarea.setSelectionRange(newCursorPos, newCursorPos)
            }, 0)
        },
        [value, onChange]
    )

    const toolbarItems = [
        { icon: Bold, action: () => insertText("**", "**"), title: t("common.bold", "Bold") },
        { icon: Italic, action: () => insertText("*", "*"), title: t("common.italic", "Italic") },
        { icon: Quote, action: () => insertText("> "), title: t("common.quote", "Quote") },
        { icon: List, action: () => insertText("- "), title: t("common.list", "List") },
        { icon: LinkIcon, action: () => insertText("[", "](url)"), title: t("common.link", "Link") },
        { icon: Code, action: () => insertText("```\n", "\n```"), title: t("common.code", "Code Block") },
    ]

    return (
        <div className={cn("flex flex-col h-full border rounded-xl bg-background overflow-hidden", className)}>
            {/* Toolbar */}
            <div className="flex items-center justify-between p-2 border-b bg-muted/30">
                <div className="flex items-center gap-1">
                    {toolbarItems.map((item) => (
                        <Button
                            key={item.title}
                            variant="ghost"
                            size="sm"
                            className="h-8 w-8 p-0"
                            onClick={item.action}
                            title={item.title}
                        >
                            <item.icon className="h-4 w-4" />
                        </Button>
                    ))}
                </div>

                <div className="flex items-center gap-1 bg-background rounded-lg p-0.5 border">
                    <Button
                        variant={viewMode === "edit" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 gap-1.5"
                        onClick={() => setViewMode("edit")}
                    >
                        <Edit3 className="h-3.5 w-3.5" />
                        {t("common.edit", "Edit")}
                    </Button>
                    <Button
                        variant={viewMode === "split" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 gap-1.5"
                        onClick={() => setViewMode("split")}
                    >
                        <SplitSquareHorizontal className="h-3.5 w-3.5" />
                        {t("common.split", "Split")}
                    </Button>
                    <Button
                        variant={viewMode === "preview" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 gap-1.5"
                        onClick={() => setViewMode("preview")}
                    >
                        <Eye className="h-3.5 w-3.5" />
                        {t("common.preview", "Preview")}
                    </Button>
                </div>
            </div>

            {/* Editor Content */}
            <div className="flex-1 flex overflow-hidden">
                {/* Editor */}
                {(viewMode === "edit" || viewMode === "split") && (
                    <div className={cn("flex flex-col", viewMode === "split" ? "w-1/2 border-r" : "w-full")}>
                        <Textarea
                            className="markdown-textarea flex-1 resize-none rounded-none border-0 font-mono text-sm leading-relaxed p-4 focus-visible:ring-0"
                            value={value}
                            onChange={(e) => onChange(e.target.value)}
                            placeholder={placeholder}
                        />
                    </div>
                )}

                {/* Preview */}
                {(viewMode === "preview" || viewMode === "split") && (
                    <div className={cn("flex flex-col bg-background", viewMode === "split" ? "w-1/2" : "w-full")}>
                        <MarkdownPreview content={value} />
                    </div>
                )}
            </div>
        </div>
    )
}
