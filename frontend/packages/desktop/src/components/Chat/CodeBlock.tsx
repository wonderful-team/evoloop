import { memo } from "react"
import { useTranslation } from "react-i18next"
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter"
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism"

interface CodeBlockProps {
  language: string
  codeString: string
  isLong: boolean
  lineCount: number
  onPreview?: (html: string) => void
}

export const CodeBlock = memo(({ language, codeString, isLong, lineCount, onPreview }: CodeBlockProps) => {
  const { t } = useTranslation()

  return (
    <div className="my-2 rounded-md overflow-hidden bg-zinc-50 dark:bg-[#1e1e1e] border border-zinc-200 dark:border-[#3e3e3e] max-w-full flex flex-col">
      <div className="flex items-center justify-between px-3 py-1 bg-zinc-100 dark:bg-[#252526] text-[10px] text-zinc-500 dark:text-gray-400 border-b border-zinc-200 dark:border-[#3e3e3e] w-full shrink-0">
        <span>
          {language} {isLong && `(${lineCount} lines)`}
        </span>
        <div className="flex items-center gap-2">
          {onPreview && (
            <button
              type="button"
              onClick={() => onPreview(codeString)}
              className="hover:text-zinc-900 dark:hover:text-white transition-colors"
            >
              {t("chat.messageList.preview", "Preview")}
            </button>
          )}
          <button
            type="button"
            onClick={() => navigator.clipboard.writeText(codeString)}
            className="hover:text-zinc-900 dark:hover:text-white transition-colors"
          >
            {t("chat.messageList.copy", "Copy")}
          </button>
        </div>
      </div>
      <div 
        className="overflow-auto relative" 
        style={{ 
          maxHeight: isLong ? "300px" : "none"
        }}
      >
        <SyntaxHighlighter
          language={language || "text"}
          style={vscDarkPlus}
          showLineNumbers={true}
          wrapLines={true}
          customStyle={{ 
            margin: 0, 
            padding: '12px',
            fontSize: '12px',
            background: 'transparent', // let the outer container handle the background
            minWidth: 'fit-content' // ensures the background stretches to the end of scrolling
          }}
          lineNumberStyle={{ 
            minWidth: '32px', 
            paddingRight: '12px', 
            color: '#6e7681', 
            textAlign: 'right',
            userSelect: 'none'
          }}
        >
          {codeString}
        </SyntaxHighlighter>
      </div>
    </div>
  )
})
