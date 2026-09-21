import { useTauriPermission } from "./useTauriPermission"

export function useScreenRecordingPermission() {
  return useTauriPermission({
    checkCommand: "check_screen_recording_permission",
    openSettingsCommand: "open_screen_recording_settings",
    label: "ScreenRecording",
  })
}
