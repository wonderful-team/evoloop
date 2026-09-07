import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@evoloop/shared/components/ui/sheet"
import { cn } from "@evoloop/shared/lib/utils"
import type { ReactNode } from "react"

/**
 * AppSheet — 应用级右侧全高抽屉的标准壳。
 *
 * 统一：响应式宽度（小屏全宽 / ≥sm 给三栏布局留 360px）、
 * chrome 层底色（bg-background-soft）、无边框（靠 shadow-2xl 浮起）、
 * 头部（图标 chip + 标题 + mono 副标题 + 右侧 actions）与底部 footer。
 *
 * 内容体由调用方提供（diff 视图 / 文件预览 / Markdown 编辑器…）。
 */
interface AppSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 主标题（同时作为 a11y SheetTitle；hideHeader 时自动转 sr-only） */
  title: ReactNode
  /** mono 副标题（通常是文件路径） */
  subtitle?: ReactNode
  /** 头部左侧图标（放在 muted chip 内） */
  icon?: ReactNode
  /** 头部右侧操作区（按钮组） */
  actions?: ReactNode
  /** 底部提示条（mono 灰阶） */
  footer?: ReactNode
  /** 隐藏可见头部（保留 sr-only 标题以满足 a11y） */
  hideHeader?: boolean
  children: ReactNode
  /** 附加到 SheetContent 的类名 */
  className?: string
}

export function AppSheet({
  open,
  onOpenChange,
  title,
  subtitle,
  icon,
  actions,
  footer,
  hideHeader = false,
  children,
  className,
}: AppSheetProps) {
  const header = hideHeader ? (
    <SheetHeader className="sr-only">
      <SheetTitle>{title}</SheetTitle>
      <SheetDescription>
        {typeof subtitle === "string" ? subtitle : undefined}
      </SheetDescription>
    </SheetHeader>
  ) : (
    (title || actions) && (
      <SheetHeader className="m-0 flex flex-row items-center justify-between gap-3 px-4 py-3 shrink-0 min-w-0">
        <div className="flex min-w-0 items-center gap-3">
          {icon && (
            <div className="flex size-9 shrink-0 items-center justify-center rounded-md border border-border bg-muted text-muted-foreground [&_svg]:size-4">
              {icon}
            </div>
          )}
          <div className="flex min-w-0 flex-col gap-1">
            <SheetTitle className="truncate text-sm font-semibold leading-none">
              {title}
            </SheetTitle>
            {subtitle && (
              <span className="truncate font-mono text-[10px] text-muted-foreground/70">
                {subtitle}
              </span>
            )}
          </div>
          <SheetDescription className="sr-only">
            {typeof subtitle === "string" ? subtitle : undefined}
          </SheetDescription>
        </div>
        {actions && (
          <div className="flex shrink-0 items-center gap-2 pr-8">{actions}</div>
        )}
      </SheetHeader>
    )
  )

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className={cn(
          "flex h-full w-full flex-col gap-0 border-l-0 p-0 shadow-2xl bg-background-soft sm:max-w-[calc(100vw-360px)]",
          className,
        )}
      >
        {header}
        {children}
        {footer}
      </SheetContent>
    </Sheet>
  )
}
