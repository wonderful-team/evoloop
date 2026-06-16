import type React from "react"
import { createContext, useCallback, useContext, useState } from "react"

interface SetupWizardContextType {
  /** Whether the setup wizard is currently open */
  isWizardOpen: boolean
  /** Set the wizard open state */
  setIsWizardOpen: (open: boolean) => void
  /**
   * Check if other dialogs should be suppressed
   * Returns true if wizard is open (other dialogs should not show)
   */
  shouldSuppressOtherDialogs: () => boolean
}

const SetupWizardContext = createContext<SetupWizardContextType | null>(null)

export function SetupWizardProvider({
  children,
}: {
  children: React.ReactNode
}) {
  const [isWizardOpen, setIsWizardOpenState] = useState(false)

  const setIsWizardOpen = useCallback((open: boolean) => {
    setIsWizardOpenState(open)
  }, [])

  const shouldSuppressOtherDialogs = useCallback(() => {
    return isWizardOpen
  }, [isWizardOpen])

  return (
    <SetupWizardContext.Provider
      value={{
        isWizardOpen,
        setIsWizardOpen,
        shouldSuppressOtherDialogs,
      }}
    >
      {children}
    </SetupWizardContext.Provider>
  )
}

export function useSetupWizard() {
  const context = useContext(SetupWizardContext)
  if (!context) {
    throw new Error("useSetupWizard must be used within SetupWizardProvider")
  }
  return context
}
