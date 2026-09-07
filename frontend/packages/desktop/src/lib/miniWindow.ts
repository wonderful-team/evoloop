import {
  LogicalSize,
  PhysicalPosition,
  PhysicalSize,
} from "@tauri-apps/api/window"
import { safeGetCurrentWindow } from "./tauri"

/**
 * 迷你模式 — 将应用窗口收缩为小窗（并置顶），退出时还原。
 *
 * 尺寸/位置快照存 localStorage，仅 Tauri 环境生效；
 * Web 预览降级由 _layout 的 CSS 卡片承担。
 */

const RESTORE_KEY = "chat.mini.restore"

export const MINI_WIDTH = 400

interface RestoreSnapshot {
  w: number
  h: number
  x: number
  y: number
}

export async function enterMiniWindow(): Promise<boolean> {
  const win = await safeGetCurrentWindow()
  if (!win) return false
  try {
    const size = await win.innerSize()
    const pos = await win.outerPosition()
    const snapshot: RestoreSnapshot = {
      w: size.width,
      h: size.height,
      x: pos.x,
      y: pos.y,
    }
    localStorage.setItem(RESTORE_KEY, JSON.stringify(snapshot))
    // 只缩宽度，高度保持不变（物理像素 → 逻辑像素）
    const scaleFactor = await win.scaleFactor()
    const logicalHeight = Math.round(size.height / scaleFactor)
    await win.setSize(new LogicalSize(MINI_WIDTH, logicalHeight))
    await win.setAlwaysOnTop(true).catch(() => {})
    return true
  } catch (e) {
    console.error("[mini] enter failed", e)
    return false
  }
}

export async function exitMiniWindow(): Promise<boolean> {
  const win = await safeGetCurrentWindow()
  if (!win) return false
  try {
    await win.setAlwaysOnTop(false).catch(() => {})
    const raw = localStorage.getItem(RESTORE_KEY)
    if (raw) {
      const { w, h, x, y } = JSON.parse(raw) as RestoreSnapshot
      await win.setSize(new PhysicalSize(w, h))
      await win.setPosition(new PhysicalPosition(x, y))
      localStorage.removeItem(RESTORE_KEY)
    }
    return true
  } catch (e) {
    console.error("[mini] exit failed", e)
    return false
  }
}
