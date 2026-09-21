import { useTauriPermission } from "./useTauriPermission"

export function useAccessibilityPermission() {
  return useTauriPermission({
    checkCommand: "check_accessibility_permission",
    openSettingsCommand: "open_accessibility_settings",
    label: "Accessibility",
  })
}
