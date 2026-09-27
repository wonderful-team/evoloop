import { expect, test } from "@playwright/test"

/**
 * Terminal keyboard input e2e — production data path, no LLM involved.
 *
 *   user keystrokes → xterm.js `onData` (TerminalCanvas.tsx:128)
 *   → chatStore.sendRawTerminalInput (coalesces with 16ms debounce)
 *   → POST /api/v1/conversations/{thread}/terminal/input {"text", "project_id"}
 *   → backend writes raw bytes into the thread's PTY master.
 *
 * The assertion boundary is the wire: a fetch spy captures the /terminal/input
 * POST and its HTTP status. The xterm instance is driven through its real
 * keyboard path (focus on the xterm helper textarea + page.keyboard.type), not
 * by calling onData directly.
 *
 * Thread isolation: this spec uses the *third* most-recent conversation, so
 * keystrokes never land in a task that `running_tasks_dock` (second slot) or
 * `terminal_render` (most recent slot) is actively running under fullyParallel.
 *
 * The chat is opened with the native hash deep-link `#/chat?thread_id=<picked>`:
 * the app is createHashHistory-based and ChatInterface now merges the hash
 * query into the params it reads — a fix that previously relied on a
 * real-query workaround because `window.location.search` alone was always
 * empty for hash URLs (which would otherwise tear down the SSE stream via
 * setThread(null)).
 */
test("terminal input: keystrokes forwarded to /terminal/input via xterm onData", async ({
  page,
}) => {
  test.setTimeout(120_000)
  await page.addInitScript(() => {
    localStorage.setItem("evoloop_setup_completed", "true")
    localStorage.setItem("evoloop_desktop_tour_seen", "true")
  })

  // Fetch spy for /terminal/input (applies before every navigation).
  await page.addInitScript(() => {
    const w = window as any
    w.__inputRequests = []
    const origFetch = w.fetch.bind(w)
    w.fetch = async (...args: any[]) => {
      const url = String(args[0])
      const res: Response = await origFetch(...args)
      if (url.includes("/terminal/input")) {
        w.__inputRequests.push({
          url,
          body: args[1]?.body ?? null,
          status: res.status,
        })
      }
      return res
    }
  })

  // Pick a thread distinct from the dock/render slots (3rd-most-recent).
  await page.goto("/#/chat")
  const picked = await page.evaluate(async () => {
    const { ConversationsService } = await import("/src/client/sdk.gen.ts")
    const res = await ConversationsService.listConversations({
      page: 1,
      pageSize: 8,
    })
    const items = (res.data || []) as Array<{
      thread_id: string
      project_id: number | null
    }>
    const chosen = items[2] ?? items[1] ?? items[0]
    return chosen
      ? { thread_id: chosen.thread_id, project_id: chosen.project_id ?? 0 }
      : null
  })
  test.skip(
    !picked,
    "need at least one existing conversation to drive live PTY",
  )

  await page.goto(`/#/chat?thread_id=${picked!.thread_id}`)
  await expect(page.locator("textarea").first()).toBeVisible({
    timeout: 30_000,
  })
  console.log("[tinput] picked thread:", picked!.thread_id, picked!.project_id)

  const threadId = picked!.thread_id
  const projectId = picked!.project_id

  // Open the thread/SSE channel, then switch ChatInterface into terminal mode
  // (the same setTerminalMode the dock pill triggers) so TerminalCanvas mounts.
  await page.evaluate(
    async ({ threadId, projectId }) => {
      const { useChatStore } = await import("/src/stores/chatStore.ts")
      const { ChatConnection } = await import("/src/lib/ChatConnection.ts")
      await useChatStore.getState().setThread(threadId, projectId)
      useChatStore.getState().setTerminalMode(true)
      const conn = ChatConnection.getInstance() as any
      const startedAt = Date.now()
      while (
        Date.now() - startedAt < 20_000 &&
        !(conn.eventSource && conn.eventSource.readyState === EventSource.OPEN)
      ) {
        await new Promise((r) => setTimeout(r, 250))
      }
    },
    { threadId, projectId },
  )

  // xterm canvas must mount and focus its helper textarea.
  const xterm = page.locator("div.xterm").first()
  await expect(xterm).toBeVisible({ timeout: 20_000 })
  await page.evaluate(() => {
    const w = window as any
    if (w.__terminal?.focus) w.__terminal.focus()
  })

  // Type through the real keyboard path.
  const typed = `ls -la; echo probe-${Date.now().toString(36)}`
  await page.keyboard.type(typed, { delay: 10 })

  // The debounced flush must hit /terminal/input with the coalesced text.
  await expect
    .poll(
      async () => {
        return page.evaluate(() => (window as any).__inputRequests?.length ?? 0)
      },
      { timeout: 15_000 },
    )
    .toBeGreaterThan(0)

  // Debounce may still be mid-coalesce when the poll flips true — give the
  // final flush(s) a moment so no trailing keystrokes are missed.
  await page.waitForTimeout(500)

  const requests = await page.evaluate(() => (window as any).__inputRequests)
  const payloads = requests
    .filter((r: any) => r.status === 200)
    .map((r: any) => JSON.parse(r.body || "{}"))
  console.log("[tinput] captured /terminal/input:", JSON.stringify(payloads))
  // Invariant: every keystroke reaches the PTY. The 16ms debounce may split the
  // typed string across MULTIPLE coalesced POSTs when the main thread stalls
  // under fullyParallel load, so concatenate all 200× payloads instead of
  // requiring one payload to contain the whole string.
  const allForwarded = payloads.map((p: any) => String(p.text || "")).join("")
  expect(allForwarded.includes(typed)).toBe(true)
  console.log("[tinput] keystrokes reached /terminal/input via onData")
})
