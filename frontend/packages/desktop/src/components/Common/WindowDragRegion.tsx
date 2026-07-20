export function WindowDragRegion() {
  return (
    <div
      data-tauri-drag-region
      style={{ WebkitAppRegion: "drag" } as any}
      className="fixed top-0 left-0 right-0 h-8 z-10 pointer-events-none select-none bg-transparent"
    />
  )
}
