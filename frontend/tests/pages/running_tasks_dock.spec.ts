import { expect, test } from "@playwright/test"

/**
 * RunningTasksDock interaction e2e — full production path.
 *
 * Data path under test (exactly the wiring that runs in the app):
 *   POST /terminal/execute (creates a BackgroundTask; publishes SSE
 *   task_created / task_started on the thread's chat channel)
 *   → ChatConnection.addEventListener("task_started")
 *   → chatStore.onTaskStatus({ task, action }) → updateActiveTask(task)
 *   → RunningTasksDock renders a TaskPill (spinner + stop button when running)
 *   → pill click → chatStore.setTerminalMode(true) → ChatInterface renders
 *     <TerminalCanvas/> (xterm visible)
 *   → stop click → chatStore.cancelTask(task_id) → POST /terminal/cancel
 *   → backend publishes task_cancelled → removeActiveTask → dock hides.
 *
 * Thread selection matters: the app uses createHashHistory, and ChatInterface's
 * init effect (plus its projectId-resolution re-run) previously resolved the
 * deep-link thread from `window.location.search` — which is empty for hash
 * URLs — so a deep link fell back to setThread(null) and DISCONNECTED the
 * EventSource mid-session. ChatInterface now merges the hash query, so the
 * test drives the real app deep-link format `#/chat?thread_id=<picked>`.
 *
 * Isolation: the test drives a conversation thread different from the one
 * `terminal_render`'s live-SSE scenario touches, so each test gets its own
 * PTY session and SSE channel even under `fullyParallel` workers.
 *
 * No LLM/chat call is made; the executed command is a bounded sleep loop that
 * the test cancels explicitly (bounded at 40s even if cancel fails).
 */
test("running tasks dock: task appears, opens terminal, stop cancels and hides", async ({
  page,
}) => {
  test.setTimeout(120_000)
  await page.addInitScript(() => {
    localStorage.setItem("evoloop_setup_completed", "true")
    // Dismiss the auto-start SpotlightTour overlay (would block pointer events).
    localStorage.setItem("evoloop_desktop_tour_seen", "true")
  })

  // Install a fetch spy for the cancel request (applies before navigation).
  await page.addInitScript(() => {
    const w = window as any
    w.__cancelRequests = []
    const origFetch = w.fetch.bind(w)
    w.fetch = async (...args: any[]) => {
      const url = String(args[0])
      if (url.includes("/terminal/cancel")) {
        w.__cancelRequests.push({ url, body: args[1]?.body ?? null })
      }
      return origFetch(...args)
    }
  })

  // Pick a thread distinct from the most-recent one (used by terminal_render
  // live scenario), falling back to it when it is the only one.
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
    const first = items[0]
    const other = items.find((item) => item.thread_id !== first?.thread_id)
    const chosen = other ?? first
    return chosen
      ? { thread_id: chosen.thread_id, project_id: chosen.project_id ?? 0 }
      : null
  })
  test.skip(
    !picked,
    "need at least one existing conversation to drive live SSE",
  )

  // Reload targeting the picked thread using the app's native deep-link format
  // (hash history puts search params inside the hash). ChatInterface reads
  // thread_id from the merged query, so the init effect selects the picked
  // thread and its projectId re-run no longer tears the EventSource down.
  await page.goto(`/#/chat?thread_id=${picked!.thread_id}`)
  await expect(page.locator("textarea").first()).toBeVisible({
    timeout: 30_000,
  })
  console.log("[dock] picked thread:", picked!.thread_id, picked!.project_id)

  const threadId = picked!.thread_id
  const projectId = picked!.project_id

  // Open the thread + SSE channel (registers onTaskStatus / onTaskOutput).
  await page.evaluate(
    async ({ threadId, projectId }) => {
      const { useChatStore } = await import("/src/stores/chatStore.ts")
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
        readyState: conn.eventSource ? conn.eventSource.readyState : null,
      }
    },
    { threadId, projectId },
  )
  console.log("[dock] setThread done")

  const MARKER = `dock-${Date.now().toString(36)}`
  const command = `echo ${MARKER}; for i in $(seq 1 40); do echo tick-$i; sleep 1; done`
  console.log("[dock] command:", command)

  const exec = await page.evaluate(
    async ({ threadId, command }) => {
      const res = await fetch(
        `/api/v1/conversations/${threadId}/terminal/execute`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command }),
        },
      )
      return await res.json()
    },
    { threadId, command },
  )
  console.log("[dock execute]", JSON.stringify(exec))
  expect(exec.task_id, "execute should return a task_id").toBeTruthy()
  const taskId = exec.task_id as string

  // The pill contains the task title (our command, marker at the front).
  const pill = page.locator("div.group", { hasText: MARKER })
  await expect(pill).toBeVisible({ timeout: 20_000 })
  console.log("[dock] pill visible")

  // Running task → spinner (loader) + a stop button inside the pill.
  await expect(
    pill.locator("button[title*='停止任务'], button[title*='Stop task']"),
  ).toBeVisible({ timeout: 20_000 })
  console.log("[dock] stop button visible (task running)")
  await page.screenshot({ path: "/tmp/ui_dock_appears.png" })

  // Click the pill → terminal mode → xterm canvas visible.
  await pill.locator("button").first().click()
  await expect(page.locator("div.xterm").first()).toBeVisible({
    timeout: 10_000,
  })
  await page.screenshot({ path: "/tmp/ui_dock_terminal.png" })

  // Stop (cancel). Dock stays mounted while the cancel POST is in flight.
  await pill
    .locator("button[title*='停止任务'], button[title*='Stop task']")
    .click()

  await expect
    .poll(
      async () => {
        return page.evaluate(
          () => (window as any).__cancelRequests?.length ?? 0,
        )
      },
      { timeout: 15_000 },
    )
    .toBeGreaterThan(0)
  const cancelledBodies = await page.evaluate(
    () => (window as any).__cancelRequests,
  )
  console.log("[dock] cancel requests:", JSON.stringify(cancelledBodies))
  const parsed = cancelledBodies
    .map((r: any) => JSON.parse(r.body || "{}"))
    .map((b: any) => b.task_id)
  expect(parsed).toContain(taskId)

  // Backend publishes task_cancelled → removeActiveTask → dock hides.
  await expect(pill).toHaveCount(0, { timeout: 20_000 })
  console.log("[dock] dock hidden after cancel")
  await page.screenshot({ path: "/tmp/ui_dock_hidden_after_cancel.png" })
})
