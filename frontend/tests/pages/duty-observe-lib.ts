/**
 * 值守 E2E 公共库：页内观测探针、服务端真相轮询、类型。
 * duty-observe / duty-full-flow 共用。
 */
import type { Page } from "@playwright/test"

import { DUTY_PROJECT_ID } from "./duty-isolation"

const KNOWN_STATUS_LITERAL = JSON.stringify([
  "pending",
  "in_progress",
  "proposed",
  "waiting_acceptance",
  "completed",
  "failed",
  "cancelled",
  "blocked",
  "confirm",
])

interface CardSample {
  id: string
  no: string
  st: string
}
interface CardsSnapshot {
  t: number
  cards: CardSample[]
}
export interface ServerTask {
  id: string
  no: number
  st: string
  updated_at?: string | null
  last_thread_id?: string | null
}

export interface DutyObs {
  sse: {
    t: number
    kind: string
    url: string | null
    name: string | null
    data: string | null
  }[]
  cards: CardsSnapshot[]
  rows: { t: number; rows: { id: string; st: string }[] }[]
  edgeLog: { t: number; edges: number }[]
  mutationTicks: { t: number; n: number }[]
  mutations: number
  lastCards: string
  lastRows: string
  lastEdges: number
}

declare global {
  interface Window {
    __dutyObs?: DutyObs
  }
}

/** 页面内安装观测探针：SSE 包装 + DOM 心跳 + 画布/列表状态采样器 */
export const OBSERVER_BOOTSTRAP = `
  const KNOWN_STATUS = ${KNOWN_STATUS_LITERAL};
  localStorage.setItem("evoloop_last_project_id", "${DUTY_PROJECT_ID}");
  localStorage.setItem("duty-experiment-notice-acked", "1");
  window.__dutyObs = {
    sse: [], cards: [], rows: [], edgeLog: [], mutationTicks: [],
    mutations: 0, lastCards: "", lastRows: "", lastEdges: -1,
  };
  const NativeES = window.EventSource;
  if (NativeES) {
    function WrappedES(url, cfg) {
      const es = new NativeES(url, cfg);
      const log = (kind, ev) => {
        try {
          let u = String(url || "");
          const i = u.indexOf("/api/");
          const shortUrl = i >= 0 ? u.slice(i) : u.slice(0, 90);
          window.__dutyObs.sse.push({
            t: Date.now(), kind, url: shortUrl,
            name: ev && ev.type ? ev.type : null,
            data: ev && ev.data ? String(ev.data).slice(0, 160) : null,
          });
        } catch (e) { /* 观测探针绝不干扰业务 */ }
      };
      es.addEventListener("open", () => log("open"));
      es.addEventListener("error", () => log("error"));
      es.addEventListener("task_queue_updated", (e) => log("event", e));
      es.addEventListener("queue_drained", (e) => log("event", e));
      return es;
    }
    WrappedES.prototype = NativeES.prototype;
    window.EventSource = WrappedES;
  }
  function startObservation() {
    new MutationObserver((muts) => { window.__dutyObs.mutations += muts.length; })
      .observe(document.documentElement, {
        subtree: true, childList: true, attributes: true, characterData: true,
      });
    setInterval(() => {
      const obs = window.__dutyObs;
      const now = Date.now();
      const cards = Array.from(document.querySelectorAll(".dc-card[data-task-id]"))
        .map((el) => {
          const cls = " " + el.className + " ";
          const st = KNOWN_STATUS.find((s) => cls.includes(" " + s + " ")) || "?";
          const noEl = el.querySelector(".dc-badge-no");
          return { id: el.getAttribute("data-task-id") || "", no: noEl ? noEl.textContent.trim() : "", st };
        });
      const sig = cards.map((c) => c.id + ":" + c.st).sort().join("|");
      if (sig !== obs.lastCards) { obs.lastCards = sig; obs.cards.push({ t: now, cards }); }
      const rows = Array.from(document.querySelectorAll("[id^='duty-task-row-']"))
        .map((el) => {
          const txt = el.textContent || "";
          const st = txt.includes("待人工验收") ? "waiting_acceptance"
            : txt.includes("评审中") ? "reviewing"
            : txt.includes("失败") ? "failed"
            : txt.includes("提案") ? "proposed"
            : el.querySelector(".animate-spin") ? "in_progress"
            : "pending/other";
          return { id: el.id, st };
        });
      const rsig = rows.map((r) => r.id + ":" + r.st).sort().join("|");
      if (rsig !== obs.lastRows) { obs.lastRows = rsig; obs.rows.push({ t: now, rows }); }
      const edges = document.querySelectorAll(".dc-edge-badge").length;
      if (edges !== obs.lastEdges) { obs.lastEdges = edges; obs.edgeLog.push({ t: now, edges }); }
      obs.mutationTicks.push({ t: now, n: obs.mutations });
      obs.mutations = 0;
    }, 500);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startObservation);
  } else {
    startObservation();
  }
`

// Node 侧轮询（page.request 带 context cookie）：高负载下页面主线程
// 被 render+观测探针占满，页内 evaluate 的 fetch 会被饿死（实测）。
export async function fetchServerTruth(page: Page): Promise<ServerTask[]> {
  // 5xx/网络抖动重试：后端重启窗口（几秒）不应让整轮 E2E 直接判死
  let lastErr: Error | null = null
  for (let i = 0; i < 6; i++) {
    try {
      const res = await page.request.get("/api/v1/tasks/queue?limit=200", {
        timeout: 15_000,
      })
      if (!res.ok()) throw new Error(`truth poll failed: HTTP ${res.status()}`)
      const j = await res.json()
      const items = (j.items ?? j.data?.items ?? []) as {
        id: string
        task_no: number
        status: string
        updated_at?: string | null
        last_thread_id?: string | null
      }[]
      return items.map((t) => ({
        id: t.id,
        no: t.task_no,
        st: t.status,
        updated_at: t.updated_at,
        last_thread_id: t.last_thread_id,
      }))
    } catch (e) {
      lastErr = e instanceof Error ? e : new Error(String(e))
      if (i === 5) break
      await page.waitForTimeout(3_000)
    }
  }
  throw lastErr ?? new Error("truth poll failed")
}

/** 取会话最新一条消息的时间戳（ISO string），作为任务真活动心跳 */
export async function fetchThreadLatestMessageTime(
  page: Page,
  threadId: string,
): Promise<string | null> {
  try {
    const res = await page.request.get(
      `/api/v1/conversations/${threadId}/messages?limit=1&offset=0`,
      { timeout: 10_000 },
    )
    if (!res.ok()) return null
    const j = await res.json()
    const msgs = (j.items ??
      (Array.isArray(j.data) ? j.data : j.data?.items) ??
      j.messages ??
      []) as Array<{ created_at?: string }>
    return msgs[0]?.created_at ?? null
  } catch {
    return null
  }
}

export function parseNo(badge: string): number | null {
  const m = badge.match(/#T-(\d+)/)
  return m ? Number(m[1]) : null
}

/**
 * 收敛容差：队列是活的——检查瞬间 recurring 任务可能刚被派发
 * （in_progress）或刚回队（pending），UI 与服务端之间允许这类瞬态差。
 * 非瞬态差（终态/提案/待验收不一致、或 pending 卡消失）才算未收敛。
 */
export function statusTolerant(server: string, ui: string): boolean {
  if (ui === server) return true
  if (ui === "(missing)") return false
  if (server === "in_progress") {
    return ui === "pending" || ui === "in_progress" || ui === "confirm"
  }
  if (server === "pending") {
    return ui === "pending" || ui === "in_progress"
  }
  return false
}
