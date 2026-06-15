import type { ReactNode } from "react"
import { type FeatureCode, useFeatureAccess } from "@/hooks/useFeatureAccess"
import { UpgradePrompt } from "./UpgradePrompt"

interface FeatureGuardProps {
  feature: FeatureCode
  children: ReactNode
  fallback?: ReactNode
}

export function FeatureGuard({
  feature,
  children,
  fallback,
}: FeatureGuardProps) {
  const { hasAccess, isExpired, requiredPlan, isLoading } =
    useFeatureAccess(feature)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    )
  }

  if (!hasAccess) {
    return (
      fallback || (
        <UpgradePrompt
          feature={feature}
          requiredPlan={requiredPlan}
          isExpired={isExpired}
        />
      )
    )
  }

  return <>{children}</>
}
