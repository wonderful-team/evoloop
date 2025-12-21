import { Link } from "@tanstack/react-router"
import { useTheme } from "@/components/theme-provider"
import { cn } from "@/lib/utils"
import icon from "/assets/images/evoloop-icon.svg"
import iconLight from "/assets/images/evoloop-icon-light.svg"

interface LogoProps {
  variant?: "full" | "icon" | "responsive"
  className?: string
  asLink?: boolean
}

export function Logo({
  variant = "full",
  className,
  asLink = true,
}: LogoProps) {
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === "dark"
  const iconLogo = isDark ? iconLight : icon

  const logoContent = (
    <div className={cn("flex items-center gap-2", className)}>
      <img
        src={iconLogo}
        alt="EvoLoop"
        className="size-8"
      />
      <span
        className={cn(
          "font-bold text-xl tracking-tight text-primary", // Use text-primary for theme consistency
          variant === "responsive" && "group-data-[collapsible=icon]:hidden",
          variant === "icon" && "hidden"
        )}
      >
        EvoLoop
      </span>
    </div>
  )

  if (!asLink) {
    return logoContent
  }

  return <Link to="/">{logoContent}</Link>
}
