/**
 * 摘要场景的 markdown 脱壳：任务描述是"Agent 可执行指令"，常带 markdown
 * 结构（清单/加粗/代码）。卡片预览与列表行空间小，全渲染会爆版式——剥掉
 * 标记符号、保留文本可读形态（展开页才用完整 MessageContent 渲染）。
 */
export function stripMarkdownTokens(input: string | null | undefined): string {
  if (!input) return ""
  let s = input

  // 代码围栏：保留内容，去掉围栏与语言标注
  s = s.replace(/```[\w-]*\n?([\s\S]*?)```/g, (_m, code: string) => code.trim())
  // 图片：整体移除（摘要里没意义）
  s = s.replace(/!\[[^\]]*\]\([^)]*\)/g, "")
  // 链接：留文字
  s = s.replace(/\[([^\]]*)\]\(([^)]*)\)/g, "$1")
  // 标题井号 / 引用符
  s = s.replace(/^#{1,6}\s+/gm, "")
  s = s.replace(/^>\s?/gm, "")
  // 无序列表符 → 间隔点（保留清单感）；有序编号是信息量，保留
  s = s.replace(/^(\s*)[-*+]\s+/gm, "$1· ")
  // 行内强调：**粗体** / `代码` / ~~删除~~（高信号、无边界歧义，直接剥）
  s = s.replace(/\*\*([^*]+)\*\*/g, "$1")
  s = s.replace(/__([^_]+)__/g, "$1")
  s = s.replace(/~~([^~]+)~~/g, "$1")
  s = s.replace(/`([^`]+)`/g, "$1")
  // 单星斜体仅在词边界剥（避免误伤 snake_case / 乘法）
  s = s.replace(/(^|[\s(（[「])\*([^*\n]+)\*(?=$|[\s.,;:!?)）\]」])/gm, "$1$2")
  // 表格分隔线行整行移除；其余行内竖线退化为分隔空格
  s = s.replace(/^\s*\|?[\s:|-]+\|[\s:|-]*$/gm, "")
  s = s.replace(/\|/g, " ")
  // 压缩连续空行，修剪首尾
  s = s.replace(/\n{3,}/g, "\n\n")
  return s.trim()
}
