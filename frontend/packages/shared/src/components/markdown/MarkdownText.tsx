import ReactMarkdown, { defaultUrlTransform } from "react-markdown"
import remarkGfm from "remark-gfm"

/**
 * 轻量 markdown 渲染（shared 通用位：任务描述 / 提案正文）。
 *
 * 与聊天 MessageContent 的分工：那个是聊天消息渲染器（thinking 拆分、
 * 视频/文件引用、代码产物解析、图片查看器），这个只做 markdown 本体：
 * GFM（表格/任务清单/删除线）+ 裸 URL autolink + URL 白名单。
 * 视觉紧凑档，适配看板卡片与描述条；主题色 token 与 shared 组件一致。
 */
const urlTransform = (url: string) => {
  if (/^(https?:|mailto:|file:)/i.test(url)) return url
  return defaultUrlTransform(url)
}

export function MarkdownText({
  content,
  className,
}: {
  content: string
  className?: string
}) {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={urlTransform}
        components={{
          a({ node: _node, children, ...props }: any) {
            return (
              <a
                {...props}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-2 break-all hover:opacity-80"
                onClick={(e) => e.stopPropagation()}
              >
                {children}
              </a>
            )
          },
          p({ children }) {
            return <p className="my-1.5 first:mt-0 last:mb-0">{children}</p>
          },
          ul({ children }) {
            return (
              <ul className="my-1.5 list-disc space-y-0.5 pl-5 first:mt-0 last:mb-0">
                {children}
              </ul>
            )
          },
          ol({ children }) {
            return (
              <ol className="my-1.5 list-decimal space-y-0.5 pl-5 first:mt-0 last:mb-0">
                {children}
              </ol>
            )
          },
          li({ children }) {
            return <li className="leading-relaxed">{children}</li>
          },
          h1({ children }) {
            return <h1 className="my-2 text-base font-bold first:mt-0">{children}</h1>
          },
          h2({ children }) {
            return <h2 className="my-2 text-[15px] font-bold first:mt-0">{children}</h2>
          },
          h3({ children }) {
            return (
              <h3 className="my-1.5 text-sm font-semibold first:mt-0">{children}</h3>
            )
          },
          h4({ children }) {
            return (
              <h4 className="my-1.5 text-sm font-semibold first:mt-0">{children}</h4>
            )
          },
          blockquote({ children }) {
            return (
              <blockquote className="my-1.5 border-l-2 border-border pl-2.5 text-muted-foreground">
                {children}
              </blockquote>
            )
          },
          code({ className, children, ...props }: any) {
            const isBlock = /language-/.test(className || "") || String(children).includes("\n")
            if (isBlock) {
              return (
                <code
                  className="my-1.5 block overflow-x-auto rounded-md bg-muted/60 p-2.5 font-mono text-[12px] leading-relaxed"
                  {...props}
                >
                  {children}
                </code>
              )
            }
            return (
              <code
                className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[0.92em]"
                {...props}
              >
                {children}
              </code>
            )
          },
          pre({ children }) {
            return <pre className="my-1.5 first:mt-0 last:mb-0">{children}</pre>
          },
          table({ children }) {
            return (
              <div className="my-1.5 overflow-x-auto">
                <table className="w-full border-collapse text-left text-[0.92em]">
                  {children}
                </table>
              </div>
            )
          },
          th({ children }) {
            return (
              <th className="border border-border bg-muted/40 px-2 py-1 font-semibold">
                {children}
              </th>
            )
          },
          td({ children }) {
            return <td className="border border-border px-2 py-1 align-top">{children}</td>
          },
          hr() {
            return <hr className="my-2 border-border" />
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
