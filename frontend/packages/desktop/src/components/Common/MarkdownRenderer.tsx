import { cn } from "@evoloop/shared/lib/utils"
import { useMemo } from "react"
import ReactMarkdown from "react-markdown"
import rehypeRaw from "rehype-raw"
import remarkGfm from "remark-gfm"
import { CodeBlock } from "@/components/Chat/CodeBlock"
import { Mermaid } from "@/components/Common/Mermaid"

export interface MarkdownRendererProps {
  content: string
  className?: string
  remarkPlugins?: any[]
  rehypePlugins?: any[]
  components?: any
}

// 1. Define static plugins outside render function to maintain reference stability
const defaultRemarkPlugins = [remarkGfm]
const defaultRehypePlugins = [rehypeRaw]

// 2. Extract static tag renderers to module level to avoid recreation on every render
const defaultComponents = {
  code({ node, inline, className, children, ...props }: any) {
    const match = /language-(\w+)/.exec(className || "")
    // react-markdown v9 removed the `inline` prop.
    // Fenced code blocks always yield children ending with '\n'; inline code never does.
    const rawChildren = String(children)
    const codeString = rawChildren.replace(/\n$/, "")
    const lineCount = codeString.split("\n").length
    const isLong = lineCount > 15
    const isBlock =
      inline === false ||
      (inline == null && (!!match || rawChildren.endsWith("\n")))

    if (isBlock && match) {
      if (match[1] === "mermaid") {
        return <Mermaid chart={codeString} />
      }
      return (
        <CodeBlock
          language={match[1]}
          codeString={codeString}
          isLong={isLong}
          lineCount={lineCount}
        />
      )
    }

    // Fenced block with no language tag — route to CodeBlock as plain text
    if (isBlock) {
      return (
        <CodeBlock
          language="text"
          codeString={codeString}
          isLong={isLong}
          lineCount={lineCount}
        />
      )
    }

    return (
      <code
        className={cn(
          "bg-muted px-1.5 py-0.5 rounded text-[85%] font-mono",
          className,
        )}
        {...props}
      >
        {children}
      </code>
    )
  },
  p: ({ children }: any) => <p className="mb-2 last:mb-0">{children}</p>,
  ul: ({ children }: any) => (
    <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>
  ),
  ol: ({ children }: any) => (
    <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>
  ),
  a: ({ href, children }: any) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline underline-offset-4 hover:opacity-80 break-all"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }: any) => (
    <blockquote className="border-l-4 border-primary/30 pl-3 italic text-muted-foreground my-2">
      {children}
    </blockquote>
  ),
  table: ({ children }: any) => (
    <div className="overflow-x-auto my-2 rounded-lg border">
      <table className="w-full text-sm text-left">{children}</table>
    </div>
  ),
  th: ({ children }: any) => (
    <th className="bg-muted px-4 py-2 font-medium border-b border-r last:border-r-0">
      {children}
    </th>
  ),
  td: ({ children }: any) => (
    <td className="px-4 py-2 border-b border-r last:border-r-0 last:border-b-0">
      {children}
    </td>
  ),
  h1: ({ children }: any) => (
    <h1 className="text-2xl font-bold mt-4 mb-4">{children}</h1>
  ),
  h2: ({ children }: any) => (
    <h2 className="text-xl font-bold mt-5 mb-3">{children}</h2>
  ),
  h3: ({ children }: any) => (
    <h3 className="text-lg font-bold mt-4 mb-2">{children}</h3>
  ),
  hr: () => <hr className="my-6 border-border" />,
  // Replace react-markdown's outer <pre> wrapper with a plain fragment so that
  // Tailwind Typography's pre styles (bg, padding, line-height) don't leak into
  // CodeBlock's own <pre> and break line-number alignment.
  pre: ({ children }: any) => <>{children}</>,
}

export function MarkdownRenderer({
  content,
  className,
  remarkPlugins = defaultRemarkPlugins,
  rehypePlugins = defaultRehypePlugins,
  components,
}: MarkdownRendererProps) {
  // 3. Use useMemo to merge custom components only when custom overrides change
  const mergedComponents = useMemo(() => {
    if (!components) return defaultComponents
    return {
      ...defaultComponents,
      ...components,
    }
  }, [components])

  return (
    <div
      className={cn("prose prose-sm max-w-none dark:prose-invert", className)}
    >
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={rehypePlugins}
        components={mergedComponents}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
