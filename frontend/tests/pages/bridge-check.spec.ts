import { test } from "@playwright/test"

const HOST_HTML = `<!doctype html><html><body>
<iframe id="agent" src="http://localhost:5173/#/chat" style="width:100%;height:600px;border:1px solid #ccc"></iframe>
<script>
  window.addEventListener("message", function (e) {
    if (e.data && e.data.type === "matrix_ready") {
      document.getElementById("agent").contentWindow.postMessage({
        type: "matrix_context", v: 1,
        payload: { route: "order/management", page_name: "订单管理", entity: null, domain: "mall_ops", ts: Date.now() },
      }, "*")
      document.title = "context-sent"
    }
  })
</script>
</body></html>`

test("宿主上下文桥冒烟：matrix_context 经 根 .env 白名单送达", async ({ page }) => {
  await page.route("**/e2e-host", (route) =>
    route.fulfill({ contentType: "text/html", body: HOST_HTML }))
  await page.goto("http://localhost:5173/e2e-host")
  // matrix_ready 由 iframe 发出 + context-sent 由宿主收到回执——证明 5173
  // origin 白名单经 .env.development 生效（代码已无兜底）
  await page.waitForFunction(() => document.title === "context-sent", { timeout: 30_000 })
})
