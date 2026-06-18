import { useTheme } from "@evoloop/shared/components/theme-provider"
import Prism from "prismjs"
import { memo, useEffect, useMemo } from "react"
import { useTranslation } from "react-i18next"
import "prismjs/components/prism-typescript"
import "prismjs/components/prism-javascript"
import "prismjs/components/prism-css"
import "prismjs/components/prism-json"
import "prismjs/components/prism-bash"
import "prismjs/components/prism-python"
import "prismjs/components/prism-markdown"
import prismLightUrl from "prismjs/themes/prism.css?url"
import prismDarkUrl from "prismjs/themes/prism-tomorrow.css?url"

interface CodeBlockProps {
  language: string
  codeString: string
  isLong: boolean
  lineCount: number
  onPreview?: (html: string) => void
}

export const CodeBlock = memo(
  ({ language, codeString, isLong, lineCount, onPreview }: CodeBlockProps) => {
    const { t } = useTranslation()
    const { resolvedTheme } = useTheme()

    useEffect(() => {
      const themeUrl = resolvedTheme === "dark" ? prismDarkUrl : prismLightUrl
      let link = document.getElementById(
        "prism-theme",
      ) as HTMLLinkElement | null
      if (!link) {
        link = document.createElement("link")
        link.id = "prism-theme"
        link.rel = "stylesheet"
        document.head.appendChild(link)
      }
      link.href = themeUrl
    }, [resolvedTheme])

    // Ensure language fallback
    const lang = Prism.languages[language] ? language : "text"

    const lineHtmlContents = useMemo(() => {
      const safeCodeString = codeString || ""
      const codeLines = safeCodeString.split("\n")
      if (lang === "text" || !Prism.languages[lang]) {
        return codeLines.map((line) =>
          line
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;"),
        )
      }
      return codeLines.map((line) =>
        Prism.highlight(line, Prism.languages[lang], lang),
      )
    }, [codeString, lang])

    return (
      <div className="not-prose my-2 rounded-md overflow-hidden bg-zinc-50 dark:bg-[#1e1e1e] border border-zinc-200 dark:border-[#3e3e3e] max-w-full flex flex-col">
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
          className="overflow-auto relative bg-zinc-50 dark:bg-[#1e1e1e] text-zinc-900 dark:text-[#d4d4d4]"
          style={{
            maxHeight: isLong ? "600px" : "none",
          }}
        >
          {/* Render each line with its line number in the same row so they stay aligned */}
          <div className="min-w-fit text-xs font-mono py-3">
            {lineHtmlContents.map((html, i) => (
              <div key={i} className="flex leading-5">
                <div className="select-none text-zinc-400 dark:text-[#6e7681] text-right pr-3 pl-3 border-r border-zinc-200 dark:border-[#3e3e3e]/30 bg-zinc-50 dark:bg-[#1e1e1e] sticky left-0 min-w-[3rem]">
                  {i + 1}
                </div>
                <div className="pl-3 pr-3 flex-1 min-w-0">
                  <pre className="m-0 p-0 bg-transparent whitespace-pre">
                    {html ? (
                      <code
                        className={`language-${lang}`}
                        dangerouslySetInnerHTML={{ __html: html }}
                      />
                    ) : (
                      <span>&nbsp;</span>
                    )}
                  </pre>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  },
)
