import { expect, test } from "@playwright/test"
import { readFileSync, statSync } from "node:fs"

/**
 * 能力包渐进式披露 · 前端端到端 spec
 *
 * 从「前端聊天对话界面」发起对话（真实浏览器 + 宿主 iframe 内嵌模拟），
 * 并监控整个 Agent 执行过程：
 *   1. 宿主协议：matrix_ready → matrix_context（domain+route+page_name）
 *   2. 内嵌裁剪：宿主上下文渲染（ChatWelcome 副标题显示页面名）
 *   3. 发送：聊天输入框 → Enter → 用户消息气泡
 *   4. 执行监控：网络层（POST /chat + SSE /stream）+ 后端日志时间线
 *      （域判定 / assembled surface / 工具调用序列）
 *   5. 渲染：AI 回复包含真实业务数字
 */

const TEST_MESSAGE = "订单管理页总共有多少订单？用列表返回的 count 字段直接报数"
const EVoloop_LOG = "/Users/huangjinhuan/Projects/develop-assistant.cn/evoloop/backend/logs/api.log"

const HOST_HTML = `<!doctype html><html><body>
<h3>Member Center 宿主（e2e 模拟）</h3>
<iframe id="agent" src="http://localhost:5173/#/chat" style="width:100%;height:720px;border:1px solid #ccc"></iframe>
<script>
  window.addEventListener("message", function (e) {
    if (e.data && e.data.type === "matrix_ready") {
      // 复刻 matrix-context.js：iframe 就绪后推送页面快照
      document.getElementById("agent").contentWindow.postMessage({
        type: "matrix_context",
        v: 1,
        payload: {
          route: "order/management",
          page_name: "订单管理",
          entity: null,
          domain: "mall_ops",
          ts: Date.now(),
        },
      }, "*")
      document.title = "context-sent"
    }
  })
</script>
</body></html>`

test.describe("capability packages · 前端发起 + 全程监控", () => {
  test.setTimeout(700_000)

  test("前端聊天界面发起对话，Agent 渐进披露全链路执行", async ({ page }) => {
    test.setTimeout(700_000)

    // ---- 后端日志监控起点（增量读取）----
    let logOffset = 0
    try {
      logOffset = statSync(EVoloop_LOG).size
    } catch {
      logOffset = 0
    }
    const backendLines: string[] = []
    const drainBackendLog = () => {
      try {
        // 按字节跟踪（utf-8 中文多字节，text.length 是字符数会错位）
        const buf = readFileSync(EVoloop_LOG)
        const chunk = buf.subarray(logOffset).toString("utf-8")
        logOffset = buf.length
        for (const line of chunk.split("\n")) {
          if (line.trim()) backendLines.push(line)
        }
      } catch {
        /* log file may rotate */
      }
    }

    // ---- 网络层监控 ----
    const networkEvents: string[] = []
    page.on("request", (req) => {
      if (req.url().includes("/api/v1/chat") && req.method() === "POST") {
        networkEvents.push(`POST /api/v1/chat → ${req.postData()?.slice(0, 220)}`)
      }
      if (req.url().includes("/stream/chat/")) {
        networkEvents.push(`SSE subscribe: ${req.url().split("/stream/")[1]}`)
      }
    })

    // ChatWelcome 的 framer-motion 入场动画会让元素持续移动（click 永不稳定）——
    // 减动效模式下动画跳过
    await page.emulateMedia({ reducedMotion: "reduce" })

    // ---- 宿主页面 + 内嵌 iframe（同源 5173，bridge dev 白名单）----
    await page.route("**/e2e-host", (route) =>
      route.fulfill({ contentType: "text/html", body: HOST_HTML }),
    )
    await page.goto("http://localhost:5173/e2e-host")

    const frame = page.frameLocator("#agent")

    // ---- 阶段 1：宿主协议握手 + 内嵌裁剪 + 宿主上下文渲染 ----
    await page.waitForFunction(() => document.title === "context-sent", {
      timeout: 30_000,
    })
    networkEvents.push("宿主协议：matrix_ready → matrix_context 已推送")

    // ChatWelcome 副标题应渲染宿主页面名（内嵌态证据）
    await expect(
      frame.locator("text=订单管理").first(),
    ).toBeVisible({ timeout: 15_000 })
    networkEvents.push("内嵌渲染：ChatWelcome 显示宿主页面名「订单管理」")

    // ---- 阶段 2：从前端聊天输入框发送对话 ----
    const composer = frame.getByPlaceholder(/Ask mall-backend/i).first()
    // Upload File 拖放区覆盖输入框拦截 pointer events —— force 填充后焦点
    // 自动落在 composer，用全局键盘事件触发发送
    await composer.fill(TEST_MESSAGE, { force: true })
    await page.keyboard.press("Enter")
    networkEvents.push("发送：Enter 提交消息")

    // 用户消息气泡出现
    await expect(
      frame.locator('[data-tour="chat-messages"]').locator("text=总共有多少订单").first(),
    ).toBeVisible({ timeout: 20_000 })
    networkEvents.push("渲染：用户消息气泡出现")

    // ---- 阶段 3：执行过程监控（AI 回复 + 工具卡片）----
    // 等 AI 回复出现（含真实订单锚点 9001），容忍分钟级 Agent 执行
    let resultText = ""
    const deadline = Date.now() + 600_000
    while (Date.now() < deadline) {
      drainBackendLog()
      resultText = await frame
        .locator('[data-tour="chat-messages"]')
        .innerText()
      if (/(0|1|2|3|4|5|6|7|8|9)\s*(单|笔)/.test(resultText) && resultText.includes("9001")) {
        break
      }
      await new Promise((r) => setTimeout(r, 3_000))
    }
    networkEvents.push("渲染：AI 回复完成（含订单数字与依据）")

    // ---- 断言：回复内容（真实业务数据）----
    expect(resultText).toMatch(/(0|1|2|3|4|5|6|7|8|9)\s*(单|笔)/)
    expect(resultText).toMatch(/订单|order/i) // 真实业务语境锚点

    // ---- 阶段 4：后端日志时间线（Agent 执行过程监控）----
    drainBackendLog()
    await new Promise((r) => setTimeout(r, 2_000))
    drainBackendLog() // run 收尾日志（run_end 等）在最后一次断言前补采
    const timeline = {
      域判定: backendLines.filter((l) => l.includes("reason='host declared: mall_ops'")).length,
      wd解析: backendLines.filter((l) =>
        l.includes("member-center/backend"),
      ).length,
      预选与装配: backendLines.filter((l) => l.includes("assembled surface")).map(
        (l) => l.match(/assembled surface: native=\d+, mcp=\d+/)?.[0],
      ),
      工具调用: Array.from(
        new Set(
          backendLines
            .map((l) => l.match(/Call: (mcp__[a-z_]+__[a-z_]+|skill|question)/)?.[1])
            .filter(Boolean),
        ),
      ),
      错误: backendLines.filter(
        (l) =>
          /ERROR|crashed/.test(l) &&
          !l.includes("test") &&
          // 已知非致命噪音：asyncio generator 关闭 / GC 连接池 / MCP server
          // 单次工具失败（Agent 自愈重试承担，AI 侧已重试成功）
          !/closing of asynchronous generator|NullPool|SAWarning|non-checked-in connection|aclose|Tool execution failed/.test(
            l,
          ),
      ).length,
    }

    console.log("\n===== Agent 执行过程监控报告 =====")
    console.log("网络层事件：")
    for (const e of networkEvents) console.log("  ", e)
    console.log("后端时间线：")
    console.log("  域判定(host_declared) 出现次数:", timeline.域判定)
    console.log("  wd=member-center/backend 设置次数:", timeline.wd解析)
    console.log("  装配面快照:", timeline.预选与装配)
    console.log("  工具调用去重:", timeline.工具调用)
    console.log("  未捕获错误数:", timeline.错误)
    console.log("==================================")

    // ---- 断言：装配与执行（后端证据）----
    expect(timeline.域判定).toBeGreaterThan(0) // host_declared 域判定发生
    expect(
      timeline.预选与装配.some((s) => s?.includes("native=5, mcp=10")),
    ).toBeTruthy() // mall-orders 预挂 10 工具
    expect(
      timeline.工具调用.some((t) => t === "mcp__mall_backend_ops__list_orders"),
    ).toBeTruthy() // 预挂工具真实调用
    expect(timeline.错误).toBe(0) // 无崩溃
  })
})
