import { memo, useMemo, useEffect } from "react"
import { useTranslation } from "react-i18next"
import Prism from "prismjs"
import "prismjs/components/prism-typescript"
import "prismjs/components/prism-javascript"
import "prismjs/components/prism-css"
import "prismjs/components/prism-json"
import "prismjs/components/prism-bash"
import "prismjs/components/prism-python"
import "prismjs/components/prism-markdown"
import "prismjs/themes/prism-tomorrow.css"

interface CodeBlockProps {
  language: string
  codeString: string
  isLong: boolean
  lineCount: number
  onPreview?: (html: string) => void
}

export const CodeBlock = memo(({ language, codeString, isLong, lineCount, onPreview }: CodeBlockProps) => {
  const { t } = useTranslation()

  // Ensure language fallback
  const lang = Prism.languages[language] ? language : "text"

  const htmlContent = useMemo(() => {
    const safeCodeString = codeString || "";
    if (lang === "text" || !Prism.languages[lang]) {
      // Escape HTML to prevent XSS
      const escaped = safeCodeString.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
      return escaped;
    }
    return Prism.highlight(safeCodeString, Prism.languages[lang], lang)
  }, [codeString, lang])

  // Simple lines for rendering line numbers
  const lines = useMemo(() => Array.from({ length: lineCount }, (_, i) => i + 1), [lineCount])

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
        className="overflow-auto relative bg-[#1e1e1e] text-[#d4d4d4]" 
        style={{ 
          maxHeight: isLong ? "300px" : "none"
        }}
      >
        {/* We use grid layout to show line numbers next to code */}
        <div className="flex text-xs font-mono min-w-fit">
          <div className="select-none text-[#6e7681] text-right pr-3 pl-3 py-3 border-r border-[#3e3e3e]/30 bg-[#1e1e1e] sticky left-0 min-w-[3rem]">
            {lines.map((i) => (
              <div key={i}>{i}</div>
            ))}
          </div>
          <pre className="p-3 m-0 min-w-fit bg-transparent text-xs" style={{ fontSize: '12px' }}>
            <code 
              className={`language-${lang}`}
              dangerouslySetInnerHTML={{ __html: htmlContent }} 
            />
          </pre>
        </div>
      </div>
    </div>
  )
})
