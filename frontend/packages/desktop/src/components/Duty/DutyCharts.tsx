import { useMemo } from "react"
import ReactECharts from "echarts-for-react"

import { useTranslation } from "react-i18next"

interface DailyPoint {
  date: string
  input_tokens: number
  output_tokens: number
  completed: number
}

/** 7-day token usage bar chart + completion trend. */
export function TokenTrendChart({ daily }: { daily: DailyPoint[] }) {
  const { t } = useTranslation()

  const option = useMemo(() => {
    const labels = daily.map((d) => d.date.slice(5)) // MM-DD
    const input = daily.map((d) => d.input_tokens)
    const output = daily.map((d) => d.output_tokens)
    const completed = daily.map((d) => d.completed)
    return {
      tooltip: { trigger: "axis" },
      legend: {
        bottom: 0,
        textStyle: { fontSize: 10 },
        itemWidth: 10,
        itemHeight: 10,
      },
      grid: { left: 8, right: 8, top: 28, bottom: 36, containLabel: true },
      xAxis: {
        type: "category",
        data: labels,
        axisLabel: { fontSize: 10 },
        axisTick: { show: false },
      },
      yAxis: [
        {
          type: "value",
          name: t("dutyBoard.chart.tokensAxis"),
          nameTextStyle: { fontSize: 10 },
          axisLabel: { fontSize: 10 },
          splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
        },
        {
          type: "value",
          name: t("dutyBoard.chart.completedAxis"),
          nameTextStyle: { fontSize: 10 },
          axisLabel: { fontSize: 10 },
          splitLine: { show: false },
        },
      ],
      series: [
        {
          name: t("dutyBoard.chart.inputTokens"),
          type: "bar",
          stack: "tokens",
          data: input,
          barMaxWidth: 18,
          itemStyle: { borderRadius: [0, 0, 0, 0] },
        },
        {
          name: t("dutyBoard.chart.outputTokens"),
          type: "bar",
          stack: "tokens",
          data: output,
          barMaxWidth: 18,
        },
        {
          name: t("dutyBoard.chart.completedTasks"),
          type: "line",
          yAxisIndex: 1,
          data: completed,
          smooth: true,
          symbolSize: 5,
        },
      ],
    }
  }, [daily, t])

  return (
    <ReactECharts
      option={option}
      notMerge
      style={{ height: 220, width: "100%" }}
      opts={{ renderer: "svg" }}
    />
  )
}

/** Status distribution donut. */
export function StatusDonut({
  counts,
}: {
  counts: Record<string, number>
}) {
  const { t } = useTranslation()

  const statusColors: Record<string, string> = {
    proposed: "#94a3b8",
    pending: "#6366f1",
    in_progress: "#f59e0b",
    self_checked: "#14b8a6",
    waiting_acceptance: "#8b5cf6",
    completed: "#22c55e",
    failed: "#ef4444",
    cancelled: "#6b7280",
  }
  const labelKeys: Record<string, string> = {
    proposed: "proposed",
    pending: "pending",
    in_progress: "inProgress",
    self_checked: "selfChecked",
    waiting_acceptance: "waiting",
    completed: "completed",
    failed: "failed",
    cancelled: "cancelled",
  }
  const data = Object.entries(counts)
    .filter(([, v]) => v > 0)
    .map(([k, v]) => ({
      name: t(`dutyBoard.state.${labelKeys[k] ?? k}`),
      value: v,
      itemStyle: { color: statusColors[k] },
    }))

  const option = useMemo(
    () => ({
      tooltip: { trigger: "item" },
      series: [
        {
          type: "pie",
          radius: ["48%", "72%"],
          center: ["50%", "50%"],
          label: { show: false },
          data,
          itemStyle: { borderColor: "#fff", borderWidth: 2 },
        },
      ],
    }),
    [data],
  )

  const total = data.reduce((s, d) => s + d.value, 0)
  return (
    <div className="relative">
      <ReactECharts
        option={option}
        notMerge
        style={{ height: 180, width: "100%" }}
        opts={{ renderer: "svg" }}
      />
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="text-center">
          <div className="text-xl font-semibold">{total}</div>
          <div className="text-[10px] text-muted-foreground">
            {t("dutyBoard.chart.totalTasks")}
          </div>
        </div>
      </div>
    </div>
  )
}
