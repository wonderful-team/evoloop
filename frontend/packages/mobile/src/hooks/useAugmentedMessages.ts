import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import type { LogMessage } from "../hooks/useEvoLoopWebSocket"

export function useAugmentedMessages(messages: LogMessage[]) {
    const { t } = useTranslation()

    return useMemo(() => {
        const results: any[] = []

        // Normalization: Ensure all have 'type' and consolidate roles
        const normalized = messages.map(m => {
            let type = m.type
            let role = m.role

            if ((m as any).role) {
                type = (m as any).role === 'user' ? 'user' : 'ai'
                role = (m as any).role
            }

            if (m.type === 'model') {
                role = 'assistant'
            }

            // Robust timestamp normalization
            let timestamp = Date.now()
            if (m.timestamp) {
                // Already in ms or seconds?
                timestamp = m.timestamp > 1e11 ? m.timestamp : m.timestamp * 1000
            } else if ((m as any).create_time) {
                const ct = (m as any).create_time
                timestamp = ct > 1e11 ? ct : ct * 1000
            } else if ((m as any).created_at) {
                timestamp = new Date((m as any).created_at).getTime()
            }

            return {
                ...m,
                type,
                role,
                timestamp
            }
        }) as LogMessage[]

        // Sort by timestamp ASC to ensure correct flow
        const sorted = [...normalized].sort((a, b) => a.timestamp - b.timestamp)

        sorted.forEach((msg, index) => {
            const prevMsg = sorted[index - 1]

            // 1. Date Separator
            let showDate = false
            let dateString = ""
            if (msg.timestamp) {
                const d = new Date(msg.timestamp)
                dateString = d.toLocaleDateString(t("common.locale"), { weekday: 'short', month: 'short', day: 'numeric' })
                const prevDate = prevMsg?.timestamp ? new Date(prevMsg.timestamp).toLocaleDateString(t("common.locale"), { weekday: 'short', month: 'short', day: 'numeric' }) : null
                if (dateString !== prevDate) {
                    showDate = true
                }
            }

            if (showDate) {
                results.push({ type: "date-separator", date: dateString })
            }

            results.push(msg)
        })

        // 2. Post-process: Pair Tool+Output -> ToolBlock
        const step2: any[] = []
        const consumedIndices = new Set<number>()

        let i = 0;
        while (i < results.length) {
            if (consumedIndices.has(i)) {
                i++
                continue
            }

            const item = results[i]

            // If tool call
            if (item.type === "tool") {
                let toolName = item.name || "Tool"
                let args = item.content

                let output = undefined
                let isFile = false
                let foundOutput = false
                let status = "running"

                try {
                    const contentObj = typeof item.content === 'string' ? JSON.parse(item.content) : item.content
                    if (contentObj && contentObj.name) {
                        toolName = contentObj.name
                    }
                    if (contentObj && contentObj.arguments) {
                        const rawArgs = contentObj.arguments
                        try {
                            args = typeof rawArgs === 'string' ? JSON.parse(rawArgs) : rawArgs
                        } catch (e) {
                            args = rawArgs
                        }
                    }
                    // Handle merged log format (embedded output)
                    if (contentObj && contentObj.output !== undefined) {
                        output = contentObj.output
                        isFile = !!contentObj.is_file_content
                        status = contentObj.status || "success"
                        foundOutput = true
                    }
                } catch (e) {
                    if (typeof item.content === 'string') {
                        const patterns = [
                            /运行\s+([\w_]+)/i,
                            /running\s+tool\s+([\w_]+)/i,
                            /running\s+([\w_]+)/i,
                            /([\w_]+)\.{3}/,
                        ]
                        for (const p of patterns) {
                            const match = item.content.match(p)
                            if (match) {
                                toolName = match[1]
                                break
                            }
                        }
                    }
                }

                // If not merged, look ahead for matching output (Backward compatibility)
                if (!foundOutput) {
                    let j = i + 1
                    while (j < results.length) {
                        if (consumedIndices.has(j)) {
                            j++
                            continue
                        }
                        const next = results[j]

                        if (next.type === "output" || next.type === "error") {
                            try {
                                const outObj = typeof next.content === 'string' ? JSON.parse(next.content) : next.content
                                if (outObj && outObj.name) {
                                    if (toolName === "Tool") {
                                        toolName = outObj.name
                                    } else if (outObj.name !== toolName) {
                                        j++;
                                        continue;
                                    }
                                }
                                output = (outObj && outObj.output !== undefined) ? outObj.output : next.content
                                isFile = !!(outObj && outObj.is_file_content)
                            } catch (e) {
                                output = next.content
                            }
                            consumedIndices.add(j)
                            foundOutput = true
                            status = (output === undefined && next.type === 'error') ? "error" : "success"
                            break
                        }

                        if (["user", "ai", "model"].includes(next.type)) break
                        j++
                    }
                }

                const toolBlock = {
                    type: "tool-block",
                    toolName: toolName,
                    content: args,
                    result: output,
                    isFile: isFile,
                    status: status,
                    timestamp: item.timestamp
                }

                // Deduplication: If we already have a tool block for this exact tool+args, 
                // and this one has more info (output) or is newer, replace it.
                const existingIdx = step2.findIndex(b =>
                    b.type === "tool-block" &&
                    b.toolName === toolName &&
                    JSON.stringify(b.content) === JSON.stringify(args) &&
                    b.status === "running" && status !== "running"
                )

                if (existingIdx !== -1) {
                    step2[existingIdx] = toolBlock
                } else {
                    step2.push(toolBlock)
                }

                i++
                continue
            }

            step2.push(item)
            i++
        }

        // 3. Post-process: Group consecutive ToolBlocks -> ToolGroup
        const finalGrouped: any[] = []
        let currentGroup: any[] = []

        const flushGroup = () => {
            if (currentGroup.length > 0) {
                let thoughtContent = undefined
                const lastItem = finalGrouped[finalGrouped.length - 1]

                if (lastItem && lastItem.type === 'thought') {
                    thoughtContent = lastItem.content
                    finalGrouped.pop()
                }

                finalGrouped.push({
                    type: "tool-group",
                    tools: [...currentGroup],
                    timestamp: currentGroup[0].timestamp,
                    thought: thoughtContent
                })
                currentGroup = []
            }
        }

        step2.forEach(item => {
            if (item.type === "tool-block") {
                currentGroup.push(item)
            } else {
                flushGroup()
                finalGrouped.push(item)
            }
        })
        flushGroup()

        // 4. Post-process: Calculate showAvatar / isRoleGrouped
        return finalGrouped.map((item, index) => {
            if (["tool-group", "date-separator", "tool-block"].includes(item.type)) {
                return item
            }

            const nextItem = finalGrouped[index + 1]
            const isLastInGroup = !nextItem || nextItem.type !== item.type || (item.role && nextItem.role !== item.role)

            return {
                ...item,
                showAvatar: isLastInGroup,
                isRoleGrouped: !isLastInGroup
            }
        })
    }, [messages, t])
}
