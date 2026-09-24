import {Card, CardContent, CardDescription, CardHeader, CardTitle,} from "@evoloop/shared/components/ui/card"
import {cn} from "@evoloop/shared/lib/utils"
import type {LucideIcon} from "lucide-react"
import type {ReactNode} from "react"

interface SettingsCardProps {
  icon?: LucideIcon
  title: string
  description?: string
  headerExtra?: ReactNode
  children: ReactNode
  className?: string
  headerClassName?: string
  iconClassName?: string
}

export function SettingsCard({
  icon: Icon,
  title,
  description,
  headerExtra,
  children,
  className,
  headerClassName,
  iconClassName,
}: SettingsCardProps) {
  return (
    <Card className={cn("overflow-hidden border-border/50 bg-card", className)}>
      <CardHeader
        className={cn("pb-1.5 border-b border-border/10", headerClassName)}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {Icon && (
              <div
                className={cn(
                  "rounded-md bg-muted/50 p-2 text-foreground/80",
                  iconClassName,
                )}
              >
                <Icon className="h-4 w-4" />
              </div>
            )}
            <div className="antialiased">
              <CardTitle className="text-base font-semibold tracking-tight">
                {title}
              </CardTitle>
              {description && (
                <CardDescription className="text-xs leading-tight mt-0.5">
                  {description}
                </CardDescription>
              )}
            </div>
          </div>
          {headerExtra && <div>{headerExtra}</div>}
        </div>
      </CardHeader>
      <CardContent className="pt-2">{children}</CardContent>
    </Card>
  )
}
