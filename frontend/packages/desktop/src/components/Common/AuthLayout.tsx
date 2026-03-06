import { Appearance } from "@/components/Common/Appearance"
import { Footer } from "./Footer"
import icon from "/assets/images/evoloop-icon.svg"

interface AuthLayoutProps {
  children: React.ReactNode
}

export function AuthLayout({ children }: AuthLayoutProps) {
  return (
    <div className="grid min-h-svh lg:grid-cols-2">
      <div className="bg-muted dark:bg-zinc-900 relative hidden lg:flex flex-col lg:items-center lg:justify-center gap-6">
        {/* Large Logo */}
        <div className="flex items-center gap-3">
          <img src={icon} alt="EvoLoop" className="size-14" />
          <span className="font-bold text-3xl tracking-tight text-primary">
            EvoLoop
          </span>
        </div>
        {/* Tagline */}
        <p className="text-lg font-medium text-gray-600 dark:text-gray-400 tracking-wide">
          拥有属于你的AI数字员工
        </p>
      </div>
      <div className="flex flex-col gap-4 p-6 md:p-10">
        <div className="flex justify-end">
          <Appearance />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <div className="w-full max-w-xs">{children}</div>
        </div>
        <Footer />
      </div>
    </div>
  )
}
