export function WindowDragRegion() {
  return (
    <div
      data-tauri-drag-region
      className="fixed top-0 left-0 right-0 h-8 z-[9999] select-none bg-black/[0.005] hover:bg-black/5 dark:hover:bg-white/5 transition-colors duration-200"
    />
  )
}
