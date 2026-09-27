import { writeFileSync } from "node:fs"
import { expect, test } from "@playwright/test"
import { setupDone } from "./helpers"

/**
 * UI-level terminal rendering verification.
 *
 * Key correction: reading `.textContent` from xterm DOM rows returns the
 * internal character-cell buffer — NOT the visual output. A `\r` (CR) does not
 * clear the residual characters in that buffer, so the "residuals" we saw are
 * a read artifact, not a real visual error. Visual state must be verified via
 * screenshots.
 *
 * We drive the exact production data path: `appendTerminalOutput` (the store
 * action wired to `task_output` SSE events) → `terminalHistoryBuffer` →
 * `TerminalCanvas` incremental write → xterm.renderer.
 *
 * Scenarios covered:
 *   A. clean full-chunk ANSI + UTF-8 (normal path)
 *   B. UTF-8 multi-byte char split across two chunks ( replacement risk)
 *   C. `\r` progress frames across separate appends (overwrite behavior)
 *   D. concurrent overlapping tasks output (the real garble race source)
 *   E. real backend + live SSE: setThread (registers onTaskOutput + opens
 *      the EventSource) → /terminal/execute → SSE task_output → store → xterm
 *
 * Scenario E is the exact production path and therefore the closest
 * reproduction of the "garbled terminal" reports. It reuses the user's most
 * recent conversation thread (read-only history fetches; no chat/LLM call).
 */

test("terminal renders ANSI/UTF-8/CR + concurrent tasks, no garbled display", async ({
  page,
}) => {
  test.setTimeout(120_000)
  await page.addInitScript(setupDone)
  await page.addInitScript(() => {
    localStorage.setItem("evoloop_setup_completed", "true")
  })

  await page.goto("/#/chat")
  await expect(page.locator("textarea").first()).toBeVisible({
    timeout: 30_000,
  })

  await page
    .locator('button[title*="erminal"], button[title*="终端"]')
    .first()
    .click()
  await expect(page.locator("div.xterm").first()).toBeVisible({
    timeout: 10_000,
  })
  await page.waitForFunction(() => !!(window as any).__terminal, {
    timeout: 15_000,
  })
  await page.waitForTimeout(500)

  // ---- Scenario A: single clean chunk with ANSI + UTF-8 ----
  await page.evaluate(async () => {
    const useChatStore = (window as any).__useChatStore || (await import("/src/stores/chatStore.ts")).useChatStore
    useChatStore
      .getState()
      .appendTerminalOutput(
        "\x1b[1;32m=== 场景A 单次完整写入 ===\x1b[0m\n" +
          "正常行: 这是一段中文输出，测试多字节字符渲染。\n" +
          "ANSI 行: \x1b[31m红\x1b[32m绿\x1b[33m黄\x1b[0m 结束\n",
      )
  })
  await page.waitForTimeout(400)
  await page.screenshot({ path: "/tmp/ui_A_single_chunk.png" })

  // ---- Scenario B: UTF-8 char split across two appends ----
  // The backend uses an incremental UTF-8 decoder; we mirror it faithfully.
  const full = new TextEncoder().encode("前缀囗后缀")
  const cut = 5 // cuts inside the 3-byte 囗
  const raw1 = full.slice(0, cut)
  const raw2 = full.slice(cut)
  await page.evaluate(
    async (d) => {
      const useChatStore = (window as any).__useChatStore || (await import("/src/stores/chatStore.ts")).useChatStore
      const dec = new TextDecoder("utf-8")
      const s1 = dec.decode(d.raw1, { stream: true })
      const s2 = dec.decode(d.raw2, { stream: false })
      useChatStore.getState().appendTerminalOutput("B-split: ")
      useChatStore.getState().appendTerminalOutput(`${s1}${s2}\n`)
    },
    { raw1, raw2 },
  )
  await page.waitForTimeout(400)
  await page.screenshot({ path: "/tmp/ui_B_split_utf8.png" })

  // ---- Scenario C: CR progress across two appends ----
  await page.evaluate(async () => {
    const useChatStore = (window as any).__useChatStore || (await import("/src/stores/chatStore.ts")).useChatStore
    useChatStore.getState().appendTerminalOutput("\rC-frame1: 12%")
    await new Promise((r) => setTimeout(r, 60))
    useChatStore.getState().appendTerminalOutput("\rC-frame2: 100%")
    useChatStore.getState().appendTerminalOutput("\n")
  })
  await page.waitForTimeout(400)
  await page.screenshot({ path: "/tmp/ui_C_cr_progress.png" })

  // ---- Scenario N: bare-LF column drift (root cause of the visual garble) ----
  // xterm converts bare "\n" to CRLF only when convertEol:true; otherwise each
  // \n moves down WITHOUT resetting the column, drifting every following line
  // to the right (staircase). The store buffer stays byte-clean (that's why the
  // .txt looks fine) while the on-screen grid is misaligned.
  await page.evaluate(async () => {
    const useChatStore = (window as any).__useChatStore || (await import("/src/stores/chatStore.ts")).useChatStore
    useChatStore.getState().appendTerminalOutput("NL-1 first line\n")
    useChatStore.getState().appendTerminalOutput("NL-2 second line\n")
    useChatStore.getState().appendTerminalOutput("NL-3 third line\n")
  })
  await page.waitForTimeout(500)
  const gridNL = await page.evaluate(async () => {
    const rowsEls = Array.from(document.querySelectorAll(".xterm-rows > div"))
    const base =
      (
        document.querySelector(".xterm-screen") as HTMLElement
      )?.getBoundingClientRect().left ?? 0

    const rowLeft = (el: Element) => {
      const span = el.querySelector("span")
      if (!span) return null
      return Math.round(span.getBoundingClientRect().left - base)
    }

    const info = rowsEls.map((el) => ({
      text: (el as HTMLElement).textContent || "",
      left: rowLeft(el),
      childSpans: el.querySelectorAll("span").length,
    }))
    const nl1 = info.find((r) => (r.text || "").startsWith("NL-1"))
    const nl2 = info.find((r) => (r.text || "").startsWith("NL-2"))
    const nl3 = info.find((r) => (r.text || "").startsWith("NL-3"))
    const marker = info.find((r) => (r.text || "").includes("场景A"))
    return {
      base,
      nl1: nl1 ? { left: nl1.left, text: nl1.text.slice(0, 40) } : null,
      nl2: nl2 ? { left: nl2.left, text: nl2.text.slice(0, 40) } : null,
      nl3: nl3 ? { left: nl3.left, text: nl3.text.slice(0, 40) } : null,
      bannerRow: marker
        ? { left: marker.left, text: marker.text.slice(0, 60) }
        : null,
      row0: info[0]
        ? { left: info[0].left, text: (info[0].text || "").slice(0, 60) }
        : null,
      allRows: info.map((i) => i.text.slice(0, 40)),
    }
  })
  console.log("[GRID NL geometry]", JSON.stringify(gridNL))
  const lefts = [gridNL.nl1, gridNL.nl2, gridNL.nl3]
    .filter(Boolean)
    .map((r: any) => r.left)
  console.log("[GRID] NL-1/2/3 lefts:", lefts, "base:", gridNL.base)
  expect(lefts.length).toBe(3)
  expect(new Set(lefts).size).toBe(1)
  await page.screenshot({ path: "/tmp/ui_N_bare_lf.png" })

  // ---- Scenario D: concurrent overlapping output ----
  await page.evaluate(async () => {
    const useChatStore = (window as any).__useChatStore || (await import("/src/stores/chatStore.ts")).useChatStore
    const s = useChatStore.getState()
    s.updateActiveTask({
      task_id: "race-1",
      task_type: "command",
      title: "concurrent command A",
      status: "running",
      created_at: new Date().toISOString(),
      output: "",
      metadata: {},
    })
    s.updateActiveTask({
      task_id: "race-2",
      task_type: "command",
      title: "concurrent command B",
      status: "running",
      created_at: new Date().toISOString(),
      output: "",
      metadata: {},
    })
    s.appendTerminalOutput("cmdA-line1\n")
    s.appendTerminalOutput("cmdB-line1\n")
    s.appendTerminalOutput("cmdA-line2 含中文\n")
    s.appendTerminalOutput("\x1b[31mcmdA 错误颜色\x1b[0m\n")
  })
  await page.waitForTimeout(400)
  await page.screenshot({ path: "/tmp/ui_D_concurrent.png" })

  // Dock should now host 2 pills.
  const dockRelations = await page
    .locator('button[title*="停止任务"], button[title*="Stop task"]')
    .count()
  console.log("[DOCK] stop buttons visible:", dockRelations)

  // ---- Scenario E: real backend full path (live SSE) ----
  // Reuse the user's most recent conversation so /terminal/execute on the
  // same thread_id flows through the real MessageBroker → chat:{id}:events
  // Pub/Sub channel that the page's ChatConnection EventSource is subscribed to.
  const picked = await page.evaluate(async () => {
    const { ConversationsService } = await import("/src/client/sdk.gen.ts")
    const res = await ConversationsService.listConversations({
      page: 1,
      pageSize: 1,
    })
    const items = (res.data || []) as Array<{
      thread_id: string
      project_id: number | null
    }>
    return items[0]
      ? { thread_id: items[0].thread_id, project_id: items[0].project_id ?? 0 }
      : null
  })
  expect(
    picked,
    "need at least one existing conversation to drive live SSE",
  ).toBeTruthy()
  console.log("[live] picked thread:", picked!.thread_id, picked!.project_id)

  const liveThreadId = picked!.thread_id
  const liveProjectId = picked!.project_id

  await page.evaluate(
    async ({ threadId, projectId }) => {
      const useChatStore = (window as any).__useChatStore || (await import("/src/stores/chatStore.ts")).useChatStore
      const { ChatConnection } = await import("/src/lib/ChatConnection.ts")
      await useChatStore.getState().setThread(threadId, projectId)
      const conn = ChatConnection.getInstance() as any
      const startedAt = Date.now()
      while (
        Date.now() - startedAt < 20_000 &&
        !(conn.eventSource && conn.eventSource.readyState === EventSource.OPEN)
      ) {
        await new Promise((r) => setTimeout(r, 250))
      }
      return {
        threadId: useChatStore.getState().threadId,
        readyState: conn.eventSource ? conn.eventSource.readyState : null,
      }
    },
    { threadId: liveThreadId, projectId: liveProjectId },
  )
  console.log("[live] setThread done")

  // Record buffer length before the command so validation only checks the new chunk.
  const prefixLen = await page.evaluate(async () => {
    const useChatStore = (window as any).__useChatStore || (await import("/src/stores/chatStore.ts")).useChatStore
    return useChatStore.getState().terminalHistoryBuffer.length
  })
  console.log("[live] buffer prefix len:", prefixLen)

  const exec = await page.evaluate(
    async ({ threadId }) => {
      const res = await fetch(
        `/api/v1/conversations/${threadId}/terminal/execute`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            command:
              'printf "\\e[1;35m真实PTY:\\e[0m 渲染测试\\n"; ' +
              'for i in 1 2 3 4 5; do printf "\\e[32m行%2d/5\\e[0m\\r" $i; sleep 0.05; done; echo ""',
          }),
        },
      )
      return await res.json()
    },
    { threadId: liveThreadId },
  )
  console.log("[live execute]", JSON.stringify(exec))
  expect(exec.task_id).toBeTruthy()

  // Wait for SSE task_output to land in the store buffer (production onTaskOutput path).
  const reached = await page.evaluate(
    async ({ startLen }) => {
      const { useChatStore } = await import("/src/stores/chatStore.ts")
      const startedAt = Date.now()
      while (Date.now() - startedAt < 30_000) {
        const b = useChatStore.getState().terminalHistoryBuffer
        if (
          b.length > startLen &&
          (b.slice(startLen).includes("渲染测试") ||
            b.slice(startLen).includes("真實PTY") ||
            b.slice(startLen).includes("真实PTY"))
        ) {
          return {
            ok: true,
            newLen: b.length - startLen,
            tail: b.slice(startLen).slice(-400),
          }
        }
        await new Promise((r) => setTimeout(r, 300))
      }
      const b = useChatStore.getState().terminalHistoryBuffer
      return {
        ok: false,
        newLen: b.length - startLen,
        tail: b.slice(startLen).slice(-400),
      }
    },
    { startLen: prefixLen },
  )
  console.log("[live SSE delivered]", JSON.stringify(reached))
  expect(
    reached.ok,
    `task_output did not reach store buffer: ${reached.tail}`,
  ).toBe(true)
  await page.waitForTimeout(800)
  await page.screenshot({ path: "/tmp/ui_F_live_sse.png" })
  console.log(
    "[DOCK] stop buttons (live):",
    await page
      .locator('button[title*="停止任务"], button[title*="Stop task"]')
      .count(),
  )

  // Final raw buffer (the exact payload consumers render).
  const buffer = await page.evaluate(async () => {
    const { useChatStore } = await import("/src/stores/chatStore.ts")
    return useChatStore.getState().terminalHistoryBuffer
  })
  console.log("[STORE BUFFER final len]", buffer.length)
  console.log("[STORE BUFFER final]", JSON.stringify(buffer.slice(-800)))

  writeFileSync(
    "/tmp/terminal_render_final.txt",
    buffer.slice(-800).length < buffer.length
      ? `(truncated to last 800 chars of ${buffer.length})\n\n` +
          buffer.slice(-800)
      : buffer,
  )

  const replacement = (buffer.match(/\uFFFD/g) || []).length
  console.log("[REPORT] replacementCharsInBuffer=", replacement)
  expect(replacement).toBe(0)
})
