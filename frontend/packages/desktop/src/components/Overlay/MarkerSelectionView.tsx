import { AnimatePresence, motion } from "framer-motion"
import { Check, Crosshair, Pin, X } from "lucide-react"
import type * as React from "react"
import { useTranslation } from "react-i18next"

export interface ExtractRegion {
  id: string
  timestamp: number
  x: number
  y: number
  width: number
  height: number
}

export interface MarkerSelectionViewProps {
  theme?: "blue" | "purple"
  isExtractMode: boolean
  isSelecting: boolean
  selectionStart: { x: number; y: number }
  selectionEnd: { x: number; y: number }
  currentMousePos: { x: number; y: number }
  extractRegions: ExtractRegion[]
  containerRef?: React.RefObject<HTMLDivElement | null>
  backgroundOverlay?: React.ReactNode
  onMouseDown: (e: React.MouseEvent) => void
  onExit: () => void
  onFloatingBallClick: () => void
}

export function MarkerSelectionView({
  theme = "blue",
  isExtractMode,
  isSelecting,
  selectionStart,
  selectionEnd,
  currentMousePos,
  extractRegions,
  containerRef,
  backgroundOverlay,
  onMouseDown,
  onExit,
  onFloatingBallClick,
}: MarkerSelectionViewProps) {
  const { t } = useTranslation()

  const isPurple = theme === "purple"
  const crosshairLineBg = isPurple ? "bg-purple-400/60" : "bg-blue-400/60"
  const centerDotBg = isPurple
    ? "bg-purple-500 shadow-purple-500/50"
    : "bg-blue-500 shadow-blue-500/50"
  const scanLineBg = isPurple
    ? "via-purple-400"
    : "via-blue-400"
  const borderPill = isPurple ? "border-purple-500/30" : "border-blue-500/30"
  const iconColor = isPurple ? "text-purple-400" : "text-blue-400"
  const selectionBorder = isPurple
    ? "border-purple-500 bg-purple-500/25 shadow-[0_0_30px_rgba(168,85,247,0.5)]"
    : "border-blue-500 bg-blue-500/25 shadow-[0_0_30px_rgba(59,130,246,0.5)]"
  const selectionBadgeBg = isPurple ? "bg-purple-500" : "bg-blue-500"
  const cornerBorder = isPurple ? "border-purple-500" : "border-blue-500"
  const ballBadgeGradient = isPurple
    ? "from-purple-500 to-pink-600 shadow-purple-500/30"
    : "from-blue-500 to-indigo-600 shadow-blue-500/30"

  const selectionStyle = () => {
    if (!isSelecting) return { opacity: 0 }
    const x = Math.min(selectionStart.x, selectionEnd.x)
    const y = Math.min(selectionStart.y, selectionEnd.y)
    const width = Math.abs(selectionEnd.x - selectionStart.x)
    const height = Math.abs(selectionEnd.y - selectionStart.y)
    return { left: x, top: y, width, height, opacity: 1 }
  }

  const crosshairHStyle = {
    left: 0,
    right: 0,
    top: currentMousePos.y,
    height: 1,
  }
  const crosshairVStyle = {
    top: 0,
    bottom: 0,
    left: currentMousePos.x,
    width: 1,
  }

  return (
    <AnimatePresence>
      {isExtractMode ? (
        <motion.div
          key="extract-mode"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          ref={containerRef}
          className="w-screen h-screen relative cursor-crosshair"
          style={{ backgroundColor: isPurple ? "rgba(255, 255, 255, 0.01)" : "rgba(0, 0, 0, 0.15)" }}
          onMouseDown={onMouseDown}
        >
          {backgroundOverlay}

          {/* Crosshair lines following cursor */}
          {!isSelecting && (
            <>
              <div
                className={`absolute pointer-events-none z-30 ${crosshairLineBg}`}
                style={crosshairHStyle}
              />
              <div
                className={`absolute pointer-events-none z-30 ${crosshairLineBg}`}
                style={crosshairVStyle}
              />
              <div
                className={`absolute w-2 h-2 rounded-full pointer-events-none z-30 -translate-x-1/2 -translate-y-1/2 shadow-lg ${centerDotBg}`}
                style={{ left: currentMousePos.x, top: currentMousePos.y }}
              />
            </>
          )}

          {/* Scanning background effect */}
          <div className="absolute inset-0 pointer-events-none overflow-hidden opacity-30">
            <motion.div
              animate={{ y: ["-10%", "110%"] }}
              transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
              className={`w-full h-0.5 bg-gradient-to-r from-transparent ${scanLineBg} to-transparent blur-sm`}
            />
          </div>

          {/* Instruction Pill */}
          <motion.div
            initial={{ y: -50, opacity: 0 }}
            animate={{ y: 32, opacity: 1 }}
            className={`absolute left-1/2 -translate-x-1/2 flex items-center gap-3 bg-slate-900/90 backdrop-blur-xl border ${borderPill} px-6 py-3 rounded-2xl shadow-2xl z-50 text-white`}
          >
            <Crosshair className={`w-5 h-5 ${iconColor}`} />
            <span className="text-sm font-semibold tracking-wide">
              {t("overlay.dragToSelect")}
            </span>
            <div className="h-4 w-[1px] bg-white/20 mx-1" />
            <span className="text-xs text-white/60 font-mono bg-white/10 px-2 py-0.5 rounded">
              {t("overlay.escToCancel")}
            </span>
          </motion.div>

          {/* Selection preview */}
          <motion.div
            className={`absolute border-2 z-40 rounded-lg ${selectionBorder}`}
            style={selectionStyle()}
          >
            {isSelecting && (
              <div
                className={`absolute -top-8 left-0 text-white text-xs font-bold px-2 py-1 rounded shadow-lg whitespace-nowrap ${selectionBadgeBg}`}
              >
                {Math.abs(selectionEnd.x - selectionStart.x)} ×{" "}
                {Math.abs(selectionEnd.y - selectionStart.y)}
              </div>
            )}
          </motion.div>

          {/* Corner markers */}
          {isSelecting && (
            <>
              <div
                className={`absolute w-4 h-4 border-l-2 border-t-2 z-50 ${cornerBorder}`}
                style={{
                  left: Math.min(selectionStart.x, selectionEnd.x) - 2,
                  top: Math.min(selectionStart.y, selectionEnd.y) - 2,
                }}
              />
              <div
                className={`absolute w-4 h-4 border-r-2 border-t-2 z-50 ${cornerBorder}`}
                style={{
                  left: Math.max(selectionStart.x, selectionEnd.x) - 14,
                  top: Math.min(selectionStart.y, selectionEnd.y) - 2,
                }}
              />
              <div
                className={`absolute w-4 h-4 border-l-2 border-b-2 z-50 ${cornerBorder}`}
                style={{
                  left: Math.min(selectionStart.x, selectionEnd.x) - 2,
                  top: Math.max(selectionStart.y, selectionEnd.y) - 14,
                }}
              />
              <div
                className={`absolute w-4 h-4 border-r-2 border-b-2 z-50 ${cornerBorder}`}
                style={{
                  left: Math.max(selectionStart.x, selectionEnd.x) - 14,
                  top: Math.max(selectionStart.y, selectionEnd.y) - 14,
                }}
              />
            </>
          )}

          {/* Exit button */}
          <motion.div
            whileHover={{ scale: 1.1 }}
            whileTap={{ scale: 0.9 }}
            className="absolute bottom-12 right-12 z-50"
          >
            <button
              onClick={onExit}
              className="h-14 w-14 rounded-full bg-red-500 text-white shadow-2xl border-2 border-white/30 flex items-center justify-center hover:bg-red-600 transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
          </motion.div>

          {/* Stats */}
          {extractRegions.length > 0 && (
            <motion.div
              initial={{ x: 50, opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              className="absolute top-8 right-8 z-50 bg-slate-900/90 backdrop-blur-xl border border-green-500/30 rounded-2xl shadow-2xl p-4 text-white"
            >
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full bg-green-500/20 flex items-center justify-center border-2 border-green-500/40">
                  <Check className="h-5 w-5 text-green-400" />
                </div>
                <div>
                  <div className="text-xs text-white/50 uppercase tracking-widest font-bold">
                    {t("overlay.marked")}
                  </div>
                  <div className="text-xl font-bold">
                    {t("overlay.regionsCount", {
                      count: extractRegions.length,
                    })}
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* Help text at bottom */}
          <div className="absolute bottom-8 left-1/2 -translate-x-1/2 text-white/60 text-sm font-medium bg-black/40 backdrop-blur-sm px-4 py-2 rounded-full">
            {t("overlay.hint")}
          </div>
        </motion.div>
      ) : (
        <motion.div
          key="floating-ball"
          initial={{ scale: 0, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          exit={{ scale: 0, opacity: 0 }}
          whileHover={{ scale: 1.05 }}
          className="w-full h-full flex items-center justify-center select-none overflow-visible group"
          onMouseDown={onMouseDown}
          onClick={onFloatingBallClick}
        >
          <div
            className="w-14 h-14 rounded-full flex items-center justify-center relative shadow-2xl transition-all duration-300 active:scale-95 border-2 border-white/50"
            style={{
              background:
                "linear-gradient(135deg, rgba(255,255,255,0.98) 0%, rgba(240,245,255,0.95) 100%)",
              backdropFilter: "blur(12px)",
              boxShadow:
                "0 8px 32px rgba(0,0,0,0.2), 0 0 0 1px rgba(255,255,255,0.5) inset",
            }}
          >
            <Pin className="w-6 h-6 text-slate-700 transition-transform group-hover:rotate-12" />

            <div
              className={`absolute inset-0 rounded-full border-2 animate-pulse pointer-events-none ${
                isPurple
                  ? "border-purple-400/30 group-hover:border-purple-400/60"
                  : "border-blue-400/30 group-hover:border-blue-400/60"
              }`}
            />

            {extractRegions.length > 0 && (
              <motion.div
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                className={`absolute -top-1 -right-1 h-6 w-6 bg-gradient-to-br text-white text-[11px] font-bold rounded-full flex items-center justify-center border-2 border-white shadow-lg ${ballBadgeGradient}`}
              >
                {extractRegions.length}
              </motion.div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
