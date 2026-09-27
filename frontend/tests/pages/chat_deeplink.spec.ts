import { expect, test } from "@playwright/test"

/**
 * Deep-link + init-effect regression coverage for the ChatInterface fixes:
 *
 *  1. `#/chat?thread_id=X` (hash-embedded query, the app's native format —
 *     createHashHistory) must select thread X on load. Before the fix the
 *     params were read from `window.location.search`, which is empty for hash
 *     URLs → the selector stayed global.
 *  2. Re-navigating to a DIFFERENT `thread_id` while already mounted must
 *     switch the active thread (reactive deep-link), keeping the EventSource
 *     open — not torn to null.
 *  3. Clearing the `thread_id` param must NOT reset the selection.
 *  4. A mid-session `currentProject` change must NOT replay the init effect's
 *     `setThread(null)` (which used to DISCONNECT the SSE stream once `projectId`
 *     resolved). The selected thread and EventSource must stay put.
 *
 * Uses threads that the dock/render/input specs do not touch (4th/5th slots) so
 * it is safe under fullyParallel.
 */
test("chat deep-link: hash thread_id select, reactive switch, no SSE teardown", async ({
  page,
}) => {
  test.setTimeout(90_000)
  await page.addInitScript(() => {
    localStorage.setItem("evoloop_setup_completed", "true")
    localStorage.setItem("evoloop_desktop_tour_seen", "true")
  })

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
    // Isolation: avoid slots 0/1/2 (used by terminal_render, running_tasks_dock,
    // terminal_input under fullyParallel).
    const a = items[3] ?? items[1] ?? items[0]
    const b = items[4] ?? items.find((t) => t.thread_id !== a.thread_id) ?? a
    return a ? { a: a.thread_id, b: b.thread_id } : null
  })
  test.skip(!picked, "need at least one conversation to drive SSE")

  const { a: threadA, b: threadB } = picked!
  console.log("[deeplink] threads:", threadA, "⇄", threadB)

  // 1) Load deep link → thread A selected, EventSource OPEN to A.
  await page.goto(`/#/chat?thread_id=${threadA}`)
  await expect(page.locator("textarea").first()).toBeVisible({
    timeout: 30_000,
  })
  let state = await page.evaluate(
    async ({ threadA }) => {
      const { useChatStore } = await import("/src/stores/chatStore.ts")
      const { ChatConnection } = await import("/src/lib/ChatConnection.ts")
      const conn = ChatConnection.getInstance() as any
      const startedAt = Date.now()
      while (
        Date.now() - startedAt < 15_000 &&
        !(
          conn.eventSource &&
          conn.eventSource.readyState === EventSource.OPEN &&
          useChatStore.getState().threadId === threadA
        )
      ) {
        await new Promise((r) => setTimeout(r, 200))
      }
      return {
        threadId: useChatStore.getState().threadId,
        readyState: conn.eventSource ? conn.eventSource.readyState : null,
        currentThreadId: conn.currentThreadId ?? null,
      }
    },
    { threadA },
  )
  console.log("[deeplink] after load:", JSON.stringify(state))
  expect(state.threadId).toBe(threadA)
  expect(state.readyState).toBe(1)
  expect(state.currentThreadId).toBe(threadA)

  // 2) SPA-navigate hash to thread B (no reload) → reactive switch to B,
  //    EventSource stays OPEN (never null).
  await page.evaluate((hash) => {
    window.location.hash = hash
  }, `#/chat?thread_id=${threadB}`)
  state = await page.evaluate(
    async ({ threadB }) => {
      const { useChatStore } = await import("/src/stores/chatStore.ts")
      const { ChatConnection } = await import("/src/lib/ChatConnection.ts")
      const conn = ChatConnection.getInstance() as any
      const startedAt = Date.now()
      while (
        Date.now() - startedAt < 15_000 &&
        !(
          useChatStore.getState().threadId === threadB &&
          conn.currentThreadId === threadB &&
          conn.eventSource &&
          conn.eventSource.readyState === EventSource.OPEN
        )
      ) {
        await new Promise((r) => setTimeout(r, 200))
      }
      return {
        threadId: useChatStore.getState().threadId,
        readyState: conn.eventSource ? conn.eventSource.readyState : null,
        currentThreadId: conn.currentThreadId ?? null,
      }
    },
    { threadB },
  )
  console.log("[deeplink] after switch:", JSON.stringify(state))
  expect(state.threadId).toBe(threadB)
  expect(state.currentThreadId).toBe(threadB)
  expect(state.readyState).toBe(1)

  // 3) Clearing the param must not reset selection.
  await page.evaluate(() => {
    window.location.hash = `#/chat`
  })
  await page.waitForTimeout(800)
  const afterClear = await page.evaluate(async () => {
    const { useChatStore } = await import("/src/stores/chatStore.ts")
    return { threadId: useChatStore.getState().threadId }
  })
  console.log("[deeplink] after clear:", JSON.stringify(afterClear))
  expect(afterClear.threadId).toBe(threadB)

  // 4) projectId resolution mid-session must NOT tear down the stream: the
  //    init effect must early-return (initRanRef) instead of replaying
  //    setThread(null) once the project resolves/changes.
  await page.evaluate(async () => {
    const { useProjectStore } = await import("/src/stores/projectStore.ts")
    useProjectStore.setState({
      currentProject: { id: 999999, name: "deeplink-verification" } as any,
    })
  })
  await page.waitForTimeout(1200)
  state = await page.evaluate(async () => {
    const { useChatStore } = await import("/src/stores/chatStore.ts")
    const { ChatConnection } = await import("/src/lib/ChatConnection.ts")
    const conn = ChatConnection.getInstance() as any
    return {
      threadId: useChatStore.getState().threadId,
      readyState: conn.eventSource ? conn.eventSource.readyState : null,
      currentThreadId: conn.currentThreadId ?? null,
    }
  })
  console.log("[deeplink] after project change:", JSON.stringify(state))
  expect(state.threadId).toBe(threadB)
  expect(state.currentThreadId).toBe(threadB)
  expect(state.readyState).toBe(1)
})
