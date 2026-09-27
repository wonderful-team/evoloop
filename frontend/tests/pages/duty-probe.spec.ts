// 诊断：浏览器侧 SSE 送达实验（与 curl 直连/curl 代理同场对照）
import { test } from "@playwright/test"
import { setupDone } from "./helpers"

test("probe: browser SSE delivery", async ({ page }) => {
  await page.addInitScript(setupDone)
  await page.addInitScript(() => {
    localStorage.setItem("duty-experiment-notice-acked", "1")
    localStorage.setItem("evoloop_last_project_id", "0")
    const w = window as unknown as { __sseRecv?: unknown[] }
    w.__sseRecv = []
    const NativeES = window.EventSource
    function WrappedES(url: string, cfg?: EventSourceInit) {
      const es = new NativeES(url, cfg)
      const short = String(url)
        .replace(/^.*\/api\//, "/api/")
        .slice(0, 60)
      es.addEventListener("open", () =>
        w.__sseRecv!.push({ t: Date.now(), kind: "open", url: short }),
      )
      es.addEventListener("task_queue_updated", (e) =>
        w.__sseRecv!.push({
          t: Date.now(),
          kind: "evt",
          name: e.type,
          data: String(e.data || "").slice(0, 80),
        }),
      )
      return es
    }
    const WrappedESAny = WrappedES as unknown as typeof EventSource
    WrappedESAny.prototype = NativeES.prototype
    window.EventSource = WrappedESAny
  })
  await page.goto("/#/duty-autonomous")
  await page.waitForTimeout(45_000)
  const recv = (await page.evaluate(
    () => (window as unknown as { __sseRecv?: unknown[] }).__sseRecv || [],
  )) as Array<{ kind: string; data?: string }>
  console.log("BROWSER-RECV:", JSON.stringify(recv.slice(0, 20)))
  console.log("BROWSER-COUNT:", recv.filter((x) => x.kind === "evt").length)
})
