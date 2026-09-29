import { mkdirSync, writeFileSync } from "node:fs"
import path from "node:path"
import { expect, type Page, test } from "@playwright/test"
import { expectNoCrash, isAuthed, setupDone } from "./helpers"

/**
 * 聊天界面 · 工具面端到端测试（chat-tool-surface）
 *
 * 仿照 scripts/evoloop_chat.py 的 5 个场景，但全部从前端 UI（/#/chat 输入框）
 * 发起，走真实链路：UI 发消息 → POST /api/v1/chat → Agent 自主决策调
 * image / video 工具 → 产物上传云端 → 回复落库。
 *
 * 场景（顺序执行）：
 *   1. 文生图   image action=generate
 *   2. 图生图   image action=generate + source=场景1产物 URL
 *   3. 文生视频 video action=generate（5s，最耗时，轮询上限 900s）
 *   4. 图片分析 image action=analyze（场景2产物）
 *   5. 视频分析 video action=analyze（场景3产物）
 *
 * 重要经验（实测）：UI 可能在轮次结束后把当前会话切到新线程（SSE 取消 +
 * 新建会话），因此不能假设同一会话——每次发送都从 POST /api/v1/chat 请求体
 * 捕获该次 thread_id，并分别轮询各自线程。
 *
 * 断言以服务端为准：轮询 /api/v1/conversations/{thread}/messages，验证
 * 媒体产物 URL（https://.../upload/chat_img|chat_video/）与分析类回复落库。
 * 全程 Playwright 录屏 1920x1080，结束保存到 videos_proof/。
 */

test.use({
  viewport: { width: 1920, height: 1080 },
  video: { mode: "on", size: { width: 1920, height: 1080 } },
})

test.skip(
  !isAuthed(),
  "chat tool-surface e2e requires E2E credentials (frontend/.env)",
)

const ARTIFACTS_DIR = path.resolve(process.cwd(), "test-results/chat-tool-surface")
const VIDEO_OUT =
  "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/videos_proof/chat-tool-surface-1920x1080.webm"

interface ThreadMessage {
  role: string
  text: string
}

/** 拉取线程消息；content 为字符串或分段数组，meta_data/references 一并拼入便于匹配产物链接。 */
async function fetchThreadMessages(
  page: Page,
  threadId: string,
): Promise<ThreadMessage[] | null> {
  return page.evaluate(async (tid) => {
    const res = await fetch(`/api/v1/conversations/${tid}/messages?limit=100`, {
      credentials: "include",
    })
    if (!res.ok) return null
    const j = await res.json()
    const items = (j.items ?? j.data?.items ?? j.data ?? []) as Array<
      Record<string, unknown>
    >
    return items.map((m) => {
      const c = m.content
      const text =
        typeof c === "string"
          ? c
          : Array.isArray(c)
            ? c
                .map((p) =>
                  typeof p === "object" && p !== null && "text" in p
                    ? String((p as { text?: string }).text ?? "")
                    : "",
                )
                .join(" ")
            : String(c ?? "")
      const meta = [
        m.meta_data ? JSON.stringify(m.meta_data) : "",
        m.references ? JSON.stringify(m.references) : "",
      ]
        .filter(Boolean)
        .join("\n")
      return { role: String(m.role ?? "?"), text: `${text}\n${meta}` }
    })
  }, threadId)
}

// 只匹配绝对 URL（meta_data.output 内是完整 https 链接；不锚定 scheme 会
// 抓出 /upload/... 相对子串，下游拿它当参考图会导致 Agent 无法拉取）
const MEDIA_RE =
  /https:\/\/[^\s()'"\]]+\/upload\/chat_(?:img|video)\/[A-Za-z0-9._/-]+?\.(?:png|jpe?g|webm|mp4)/g

function extractMedia(text: string, exts: "image" | "video"): string[] {
  const all = [...text.matchAll(MEDIA_RE)].map((m) => m[0])
  return all.filter((u) =>
    exts === "image" ? /\.(png|jpe?g|webm)$/.test(u) : /\.mp4$/.test(u),
  )
}

/** UI 输入框发送一条消息，并从 POST /api/v1/chat 请求体捕获该次 thread_id。 */
async function sendChat(page: Page, message: string): Promise<string> {
  const input = page.locator("textarea").first()
  await expect(input).toBeVisible({ timeout: 15_000 })
  const chatRespPromise = page.waitForResponse(
    (r) => {
      if (r.request().method() !== "POST") return false
      try {
        return new URL(r.url()).pathname === "/api/v1/chat"
      } catch {
        return false
      }
    },
    { timeout: 60_000 },
  )
  await input.fill(message)
  await input.press("Enter")
  const resp = await chatRespPromise
  let threadId: string | null = null
  try {
    const body = resp.request().postDataJSON() as { thread_id?: string }
    threadId = body?.thread_id ?? null
  } catch {
    threadId = null
  }
  if (!threadId) {
    try {
      const j = (await resp.json()) as { thread_id?: string }
      threadId = j.thread_id ?? null
    } catch {
      threadId = null
    }
  }
  expect(threadId, "POST /api/v1/chat 未携带/返回 thread_id").toBeTruthy()
  return threadId as string
}

/** 轮询线程消息直到条件满足；超时抛错并附最近状态。 */
async function pollThread(
  page: Page,
  threadId: string,
  check: (args: { full: string; msgs: ThreadMessage[] }) => boolean,
  timeoutMs: number,
  label: string,
): Promise<ThreadMessage[]> {
  const deadline = Date.now() + timeoutMs
  let lastLog = "null"
  while (Date.now() < deadline) {
    const msgs = await fetchThreadMessages(page, threadId)
    if (msgs !== null) {
      const full = msgs.map((m) => m.text).join("\n")
      lastLog = `${msgs.length} msgs`
      if (check({ full, msgs })) return msgs
    }
    await page.waitForTimeout(5_000)
  }
  throw new Error(`[超时] ${label}: ${timeoutMs}ms 内未满足条件（last=${lastLog}）`)
}

/** 确认消息已落到目标线程（兜住 UI 静默丢发送/线程切换）。 */
async function awaitMessageLanded(
  page: Page,
  threadId: string,
  marker: string,
): Promise<void> {
  await pollThread(
    page,
    threadId,
    ({ full }) => full.includes(marker),
    60_000,
    `消息落库（marker=${marker.slice(0, 20)}…）`,
  )
}

/** 断言 marker 之后的最后一条 assistant 回复（分析类场景；拼接会被串扰满足）。 */
function assistantReplyAfter(msgs: ThreadMessage[], marker: string): string {
  const idx = msgs.findIndex((m) => m.text.includes(marker))
  if (idx < 0) return ""
  const replies = msgs
    .slice(idx + 1)
    .filter((m) => /assistant|agent|ai/.test(m.role) && m.text.trim().length > 0)
  return replies.length > 0 ? (replies.at(-1) as ThreadMessage).text : ""
}

/** 尽力等待会话静默（轮次收尾）；失败不阻塞主流程。 */
async function awaitQuiescent(
  page: Page,
  threadId: string,
  timeoutMs = 180_000,
): Promise<void> {
  try {
    const deadline = Date.now() + timeoutMs
    let lastCount = -1
    let stable = 0
    while (Date.now() < deadline) {
      const msgs = await fetchThreadMessages(page, threadId)
      if (msgs !== null && msgs.length > 0) {
        const last = msgs.at(-1) as ThreadMessage
        if (msgs.length === lastCount && /assistant|agent|ai/.test(last.role)) {
          stable += 1
          if (stable >= 2) return
        } else {
          stable = 0
        }
        lastCount = msgs.length
      }
      await page.waitForTimeout(4_000)
    }
  } catch {
    // best-effort：静默启发式失败不视为用例失败
  }
}

test("chat UI: image/video tool surface (t2i, i2i, t2v, image & video analyze)", async ({
  page,
}) => {
  test.setTimeout(2_400_000)
  mkdirSync(ARTIFACTS_DIR, { recursive: true })
  mkdirSync(path.dirname(VIDEO_OUT), { recursive: true })

  const pageErrors: string[] = []
  page.on("pageerror", (err) => {
    if (pageErrors.length < 20) pageErrors.push(String(err).slice(0, 300))
  })

  await page.addInitScript(setupDone)
  await page.addInitScript(() => {
    localStorage.setItem("evoloop_desktop_tour_seen", "true")
  })
  await page.goto("/#/chat")
  await expectNoCrash(page)
  await expect(page.locator("textarea").first()).toBeVisible({
    timeout: 30_000,
  })
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, "00-chat-ready.png") })

  const threads: Record<string, string> = {}

  // ── 场景 1：文生图 ──────────────────────────────────────────────
  const ts = Date.now()
  const marker1 = `【UI文生图 ${ts}】`
  threads.s1 = await sendChat(
    page,
    `${marker1}请调用 image 工具（action=generate）生成一张图：一只柴犬戴宇航员头盔在月球上散步，远处能看到地球，卡通风格，尺寸 1024x1024。`,
  )
  await awaitMessageLanded(page, threads.s1, marker1)
  console.log("[chat-tool-surface] s1 thread:", threads.s1)

  let msgs = await pollThread(
    page,
    threads.s1,
    ({ full }) => extractMedia(full, "image").length > 0,
    300_000,
    "文生图（等待 chat_img 产物 URL）",
  )
  const img1 = extractMedia(msgs.map((m) => m.text).join("\n"), "image").at(
    -1,
  ) as string
  console.log("[chat-tool-surface] s1 t2i →", img1)
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, "01-t2i.png") })
  await awaitQuiescent(page, threads.s1)

  // ── 场景 2：图生图（以场景 1 产物为参考图）──────────────────────
  const marker2 = `【UI图生图 ${ts}】`
  threads.s2 = await sendChat(
    page,
    `${marker2}请调用 image 工具做图生图（action=generate 并传 source 参考图）：参考图 ${img1} （公网可访问）。请直接调用工具执行图生图，把画面里的柴犬换成一只橘猫，其余构图和风格保持一致，尺寸 1024x1024，不要向我确认。`,
  )
  await awaitMessageLanded(page, threads.s2, marker2)
  console.log("[chat-tool-surface] s2 thread:", threads.s2)

  msgs = await pollThread(
    page,
    threads.s2,
    ({ full }) => {
      const urls = extractMedia(full, "image")
      return urls.some((u) => u !== img1)
    },
    300_000,
    "图生图（等待新的 chat_img 产物 URL）",
  )
  const img2 = extractMedia(msgs.map((m) => m.text).join("\n"), "image")
    .filter((u) => u !== img1)
    .at(-1) as string
  console.log("[chat-tool-surface] s2 i2i →", img2)
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, "02-i2i.png") })
  await awaitQuiescent(page, threads.s2)

  // ── 场景 3：文生视频（最耗时，轮询上限 900s）───────────────────
  const marker3 = `【UI文生视频 ${ts}】`
  threads.s3 = await sendChat(
    page,
    `${marker3}请调用 video 工具（action=generate）生成一段 5 秒的短视频：海浪拍打礁石，夕阳西下，电影感，尺寸 1280x720。`,
  )
  await awaitMessageLanded(page, threads.s3, marker3)
  console.log("[chat-tool-surface] s3 thread:", threads.s3)

  msgs = await pollThread(
    page,
    threads.s3,
    ({ full }) => extractMedia(full, "video").length > 0,
    900_000,
    "文生视频（等待 chat_video 产物 URL）",
  )
  const vid1 = extractMedia(msgs.map((m) => m.text).join("\n"), "video").at(
    -1,
  ) as string
  console.log("[chat-tool-surface] s3 t2v →", vid1)
  await page.screenshot({ path: path.join(ARTIFACTS_DIR, "03-t2v.png") })
  await awaitQuiescent(page, threads.s3)

  // ── 场景 4：图片分析（分析场景 2 产物）─────────────────────────
  const marker4 = `【UI图片分析 ${ts}】`
  threads.s4 = await sendChat(
    page,
    `${marker4}请调用 image 工具（action=analyze）分析这张图片的内容和构图：${img2}`,
  )
  await awaitMessageLanded(page, threads.s4, marker4)
  console.log("[chat-tool-surface] s4 thread:", threads.s4)

  msgs = await pollThread(
    page,
    threads.s4,
    ({ msgs: m }) => assistantReplyAfter(m, marker4).length > 120,
    240_000,
    "图片分析（等待 assistant 分析回复）",
  )
  const imgAnalysis = assistantReplyAfter(msgs, marker4)
  console.log(
    "[chat-tool-surface] s4 image analyze:",
    imgAnalysis.slice(0, 120),
  )
  await page.screenshot({
    path: path.join(ARTIFACTS_DIR, "04-image-analyze.png"),
  })
  await awaitQuiescent(page, threads.s4)

  // ── 场景 5：视频分析（分析场景 3 产物）─────────────────────────
  const marker5 = `【UI视频分析 ${ts}】`
  threads.s5 = await sendChat(
    page,
    `${marker5}请调用 video 工具（action=analyze）分析这段视频的内容：${vid1}`,
  )
  await awaitMessageLanded(page, threads.s5, marker5)
  console.log("[chat-tool-surface] s5 thread:", threads.s5)

  msgs = await pollThread(
    page,
    threads.s5,
    ({ msgs: m }) => assistantReplyAfter(m, marker5).length > 120,
    360_000,
    "视频分析（等待 assistant 分析回复）",
  )
  const vidAnalysis = assistantReplyAfter(msgs, marker5)
  console.log(
    "[chat-tool-surface] s5 video analyze:",
    vidAnalysis.slice(0, 120),
  )
  await page.screenshot({
    path: path.join(ARTIFACTS_DIR, "05-video-analyze.png"),
  })

  writeFileSync(
    path.join(ARTIFACTS_DIR, "result.json"),
    JSON.stringify(
      {
        threads,
        t2i: img1,
        i2i: img2,
        t2v: vid1,
        imageAnalysisPreview: imgAnalysis.slice(0, 300),
        videoAnalysisPreview: vidAnalysis.slice(0, 300),
      },
      null,
      2,
    ),
  )

  expect(pageErrors, "页面存在未捕获异常").toEqual([])

  const video = page.video()
  if (video) {
    await page.close()
    await video.saveAs(VIDEO_OUT)
    console.log("SAVED_VIDEO_TO:", VIDEO_OUT)
  }
})
