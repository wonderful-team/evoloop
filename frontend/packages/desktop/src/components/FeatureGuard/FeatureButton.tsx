import { Button } from "@evoloop/shared/components/ui/button"
import { Lock, Loader2 } from "lucide-react"
import { useFeatureAccess, type FeatureCode } from "@/hooks/useFeatureAccess"
import { cn } from "@evoloop/shared/lib/utils"
import { useTranslation } from "react-i18next"

interface FeatureButtonProps {
  feature: FeatureCode
  children: React.ReactNode
  onClick?: () => void
  variant?: "default" | "secondary" | "outline" | "ghost" | "link"
  size?: "default" | "sm" | "lg" | "icon"
  className?: string
  disabled?: boolean
  showLockIcon?: boolean
}

export function FeatureButton({
  feature,
  children,
  onClick,
  variant = "default",
  size = "default",
  className,
  disabled,
  showLockIcon = true,
}: FeatureButtonProps) {
  const { t } = useTranslation()
  const { hasAccess, requiredPlan, isLoading } = useFeatureAccess(feature)

  if (isLoading) {
    return (
      <Button variant={variant} size={size} className={className} disabled>
        <Loader2 className="h-4 w-4 animate-spin" />
      </Button>
    )
  }

  if (!hasAccess) {
    return (
      <Button
        variant="outline"
        size={size}
        className={cn("opacity-60 hover:opacity-80", className)}
        onClick={() => {
          window.location.hash = "#/subscription"
        }}
        title={t('subscription.upgradeRequired', { plan: t(`subscription.plans.${requiredPlan}`) })}
      >
        {showLockIcon && <Lock className="h-3.5 w-3.5 mr-1" />}
        {children}
        <span className="ml-1 text-xs text-muted-foreground opacity-70">
          ({t(`subscription.plans.${requiredPlan}`)})
        </span>
      </Button>
    )
  }

  return (
    <Button
      variant={variant}
      size={size}
      className={className}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </Button>
  )
}
