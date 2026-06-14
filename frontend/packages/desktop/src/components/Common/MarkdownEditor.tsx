/**
 * MarkdownEditor - A markdown editor with live preview using Monaco Editor
 */

import { useState } from "react"
import { Eye, Edit3, SplitSquareHorizontal } from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { CodeBlock } from "@/components/Chat/CodeBlock"
import { Button } from "@evoloop/shared/components/ui/button"
import { cn } from "@evoloop/shared/lib/utils"
import { useTranslation } from "react-i18next"
import MonacoEditor from "./MonacoEditor"

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
                                            {t("chat.messageList.copy")}
                                        </button>
                                    </div>
                                    <CodeBlock
                                        language={match[1]}
                                        code={codeString}
                                    />
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
                {content || t("learning.editor.noContent")}
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


    return (
        <div className={cn("flex flex-col h-full border rounded-xl bg-background overflow-hidden", className)}>
            {/* Toolbar */}
            <div className="flex items-center justify-between p-2 border-b border-border bg-muted/30 shrink-0">
                <div className="flex items-center gap-1">
                    {/* Placeholder for potential future toolbar items */}
                </div>

                <div className="flex items-center gap-1 bg-background rounded-lg p-0.5 border">
                    <Button
                        variant={viewMode === "edit" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 gap-1.5"
                        onClick={() => setViewMode("edit")}
                    >
                        <Edit3 className="h-3.5 w-3.5" />
                        {t("common.edit")}
                    </Button>
                    <Button
                        variant={viewMode === "split" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 gap-1.5"
                        onClick={() => setViewMode("split")}
                    >
                        <SplitSquareHorizontal className="h-3.5 w-3.5" />
                        {t("common.split")}
                    </Button>
                    <Button
                        variant={viewMode === "preview" ? "secondary" : "ghost"}
                        size="sm"
                        className="h-7 gap-1.5"
                        onClick={() => setViewMode("preview")}
                    >
                        <Eye className="h-3.5 w-3.5" />
                        {t("common.preview")}
                    </Button>
                </div>
            </div>

            {/* Editor Content */}
            <div className="flex-1 flex overflow-hidden">
                {/* Editor */}
                {(viewMode === "edit" || viewMode === "split") && (
                    <div className={cn("flex flex-col", viewMode === "split" ? "w-1/2 border-r" : "w-full")}>
                        <MonacoEditor
                            language="markdown"
                            value={value}
                            onChange={onChange}
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
