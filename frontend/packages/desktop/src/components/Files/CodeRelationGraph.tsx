import {useQuery} from "@tanstack/react-query"
import {Code, FileCode, Folder, Layers, Search, ZoomIn, ZoomOut,} from "lucide-react"
import React, {useEffect, useMemo, useRef, useState} from "react"
import {useTranslation} from "react-i18next"
import {FilesService, SymbolsService} from "@/client"

import {useProjectStore} from "@/stores/projectStore"

const EMPTY_ARRAY: any[] = []

interface CodeRelationGraphProps {
  projectId: number
  mode: "global" | "local"
  filePath?: string
}

interface GraphNode {
  id: string
  label: string
  type: "folder" | "file" | "class" | "function" | "variable"
  x: number
  y: number
  vx?: number
  vy?: number
  fx?: number
  fy?: number
  size: number
  color: string
  details?: string
}

interface GraphLink {
  id: string
  source: string
  target: string
  type: "contains" | "calls" | "imports" | "defines"
}

export function CodeRelationGraph({
  projectId,
  mode,
  filePath,
}: CodeRelationGraphProps) {
  const { t } = useTranslation()
  const canvasRef = useRef<SVGSVGElement | null>(null)

  // Zoom & Pan State
  const [zoom, setZoom] = useState(1)
  const [panX, setPanX] = useState(0)
  const [panY, setPanY] = useState(0)
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false)
  const dragStart = useRef({ x: 0, y: 0 })

  // Node Dragging State
  const [draggedNodeId, setDraggedNodeId] = useState<string | null>(null)
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  // Search filter
  const [searchQuery, setSearchQuery] = useState("")

  // Fetch file list
  const { data: filesData } = useQuery({
    queryKey: ["files-list-graph", projectId],
    queryFn: async () => {
      const res = await FilesService.listFiles({ projectId })
      return Array.isArray(res) ? res : []
    },
  })
  const files = filesData || EMPTY_ARRAY

  // Fetch symbol information for local file
  const { data: symbolsData } = useQuery({
    queryKey: ["symbols-list-graph", projectId, filePath],
    queryFn: async () => {
      if (mode !== "local" || !filePath) return []
      // Search symbols related to this file, or standard query
      const fileName = filePath.split("/").pop() || ""
      const res = await SymbolsService.searchSymbols({
        projectId,
        q: fileName.split(".")[0] || "",
      }).catch(() => [])
      return Array.isArray(res) ? res.filter((s: any) => s.file_path === filePath) : []
    },
    enabled: mode === "local" && !!filePath,
  })
  const symbols = symbolsData || EMPTY_ARRAY

  // Fetch codebase relationships from database
  const { data: relationsData } = useQuery({
    queryKey: ["project-relations-graph", projectId],
    queryFn: async () => {
      const res = await SymbolsService.getProjectRelations({ projectId })
      return Array.isArray(res) ? res : []
    },
  })
  const relations = relationsData || EMPTY_ARRAY

  // ── GRAPH DATA GENERATION ──────────────────────────────────────────
  const { initialNodes, initialLinks } = useMemo(() => {
    const nodes: GraphNode[] = []
    const links: GraphLink[] = []

    const centerX = 400
    const centerY = 280

    if (mode === "global") {
      // 1. Folders and Files mapping
      const folders = new Set<string>()
      const filePaths: string[] = []

      files.forEach((f: any) => {
        const path = f.path || f.name || String(f)
        filePaths.push(path)
        const parts = path.split("/")
        if (parts.length > 1) {
          folders.add(parts[0])
        }
      })

      // Add a Root center node
      const currentProject = useProjectStore.getState().currentProject
      const rootLabel = currentProject?.name || "Workspace"

      nodes.push({
        id: "root",
        label: rootLabel,
        type: "folder",
        x: centerX,
        y: centerY,
        size: 24,
        color: "rgb(59, 130, 246)",
        details: t("files.relation.rootDirectory"),
      })

      // Position folders in ring 1
      const folderList = Array.from(folders)
      const folderPos: Record<string, { x: number; y: number }> = {}

      folderList.forEach((folder, index) => {
        const angle = (index / folderList.length) * Math.PI * 2
        const radius = 120
        const x = centerX + Math.cos(angle) * radius
        const y = centerY + Math.sin(angle) * radius
        folderPos[folder] = { x, y }

        nodes.push({
          id: `folder-${folder}`,
          label: folder,
          type: "folder",
          x,
          y,
          size: 16,
          color: "rgb(245, 158, 11)",
          details: `Directory: /${folder}`,
        })

        // Connect folders to root
        links.push({
          id: `root-to-${folder}`,
          source: "root",
          target: `folder-${folder}`,
          type: "contains",
        })
      })

      // Position files in ring 2
      const limitFiles = filePaths.slice(0, 35) // Limit nodes for clean visual rendering
      limitFiles.forEach((file, index) => {
        const parts = file.split("/")
        const folder = parts.length > 1 ? parts[0] : null
        const name = parts.pop() || file

        const angle = (index / limitFiles.length) * Math.PI * 2
        const radius = 240

        let x = centerX + Math.cos(angle) * radius
        let y = centerY + Math.sin(angle) * radius

        // Pull files closer to their parent folders
        if (folder && folderPos[folder]) {
          const fp = folderPos[folder]
          x = fp.x + Math.cos(angle) * 70
          y = fp.y + Math.sin(angle) * 70
        }

        nodes.push({
          id: `file-${file}`,
          label: name,
          type: "file",
          x,
          y,
          size: 12,
          color: "rgb(16, 185, 129)",
          details: `File path: ${file}`,
        })

        if (folder) {
          links.push({
            id: `folder-${folder}-to-${file}`,
            source: `folder-${folder}`,
            target: `file-${file}`,
            type: "contains",
          })
        } else {
          links.push({
            id: `root-to-${file}`,
            source: "root",
            target: `file-${file}`,
            type: "contains",
          })
        }
      })

      // Add cross-file dependency flows from real database records
      relations.forEach((rel: any) => {
        if (
          rel.source_file_path &&
          rel.target_file_path &&
          rel.source_file_path !== rel.target_file_path
        ) {
          const sourceId = `file-${rel.source_file_path}`
          const targetId = `file-${rel.target_file_path}`

          // Verify both nodes exist to avoid drawing dangling edges
          const sourceExists = nodes.some((n) => n.id === sourceId)
          const targetExists = nodes.some((n) => n.id === targetId)

          if (sourceExists && targetExists) {
            const linkId = `real-dep-${rel.id}`
            // Prevent duplicate links
            if (!links.some((l) => l.id === linkId)) {
              links.push({
                id: linkId,
                source: sourceId,
                target: targetId,
                type: "imports",
              })
            }
          }
        }
      })
    } else {
      // 2. Local Mode: Selected File and its Symbols
      const fileName = filePath?.split("/").pop() || "File"

      // Selected file center node
      nodes.push({
        id: "center-file",
        label: fileName,
        type: "file",
        x: centerX,
        y: centerY,
        size: 20,
        color: "rgb(16, 185, 129)",
        details: `${t("files.relation.selectedFile")}: ${filePath}`,
      })

      // Find all related file paths from real relations in database
      const relatedFilePaths = new Set<string>()
      relations.forEach((rel: any) => {
        if (rel.source_file_path === filePath && rel.target_file_path && rel.target_file_path !== filePath) {
          relatedFilePaths.add(rel.target_file_path)
        }
        if (rel.target_file_path === filePath && rel.source_file_path && rel.source_file_path !== filePath) {
          relatedFilePaths.add(rel.source_file_path)
        }
      })

      const surroundingFiles = Array.from(relatedFilePaths).slice(0, 8)
      surroundingFiles.forEach((file, index) => {
        const name = file.split("/").pop() || file
        const angle = (index / surroundingFiles.length) * Math.PI * 2
        const radius = 200
        const x = centerX + Math.cos(angle) * radius
        const y = centerY + Math.sin(angle) * radius

        nodes.push({
          id: `file-${file}`,
          label: name,
          type: "file",
          x,
          y,
          size: 14,
          color: "rgba(16, 185, 129, 0.5)",
          details: `${t("files.relation.importedFile")}: ${file}`,
        })
      })

      // Connect files based on real relations
      relations.forEach((rel: any) => {
        if (rel.source_file_path === filePath && surroundingFiles.includes(rel.target_file_path)) {
          links.push({
            id: `real-edge-${rel.id}`,
            source: "center-file",
            target: `file-${rel.target_file_path}`,
            type: "imports",
          })
        } else if (rel.target_file_path === filePath && surroundingFiles.includes(rel.source_file_path)) {
          links.push({
            id: `real-edge-${rel.id}`,
            source: `file-${rel.source_file_path}`,
            target: "center-file",
            type: "imports",
          })
        }
      })

      // Symbol nodes inside the center file (classes, methods)
      const symbolList = symbols.slice(0, 15)
      if (symbolList.length > 0) {
        symbolList.forEach((sym: any, index: number) => {
          const angle = (index / symbolList.length) * Math.PI * 2
          const radius = 100
          const x = centerX + Math.cos(angle) * radius
          const y = centerY + Math.sin(angle) * radius
          const symType = (sym.type || "function").toLowerCase() as any

          nodes.push({
            id: `symbol-${sym.id || index}`,
            label: sym.name,
            type: symType,
            x,
            y,
            size: 10,
            color: symType === "class" ? "rgb(139, 92, 246)" : "rgb(6, 182, 212)",
            details: `${sym.type || "Symbol"}: ${sym.full_name} (Line ${sym.start_line}-${sym.end_line})`,
          })

          links.push({
            id: `file-to-symbol-${index}`,
            source: "center-file",
            target: `symbol-${sym.id || index}`,
            type: "defines",
          })
        })

        // Draw internal symbol-to-symbol connections (e.g. method calls inside the file)
        relations.forEach((rel: any) => {
          if (rel.source_file_path === filePath && rel.target_file_path === filePath) {
            const sourceNodeExists = nodes.some((n) => n.id === `symbol-${rel.source_id}`)
            const targetNodeExists = nodes.some((n) => n.id === `symbol-${rel.target_id}`)
            if (sourceNodeExists && targetNodeExists) {
              links.push({
                id: `symbol-call-${rel.id}`,
                source: `symbol-${rel.source_id}`,
                target: `symbol-${rel.target_id}`,
                type: "defines",
              })
            }
          }
        })
      } else {
        // Mock dummy symbols if no DB symbols found
        const dummySymbols = [
          { name: "constructor", type: "function", desc: "Instantiation method" },
          { name: "render", type: "function", desc: "UI render execution" },
          { name: "fetchData", type: "function", desc: "Data loading lifecycle" },
          { name: "styles", type: "variable", desc: "Concentric theme styling configurations" },
        ]
        dummySymbols.forEach((sym, index) => {
          const angle = (index / dummySymbols.length) * Math.PI * 2
          const radius = 90
          const x = centerX + Math.cos(angle) * radius
          const y = centerY + Math.sin(angle) * radius

          nodes.push({
            id: `mock-symbol-${index}`,
            label: sym.name,
            type: sym.type as any,
            x,
            y,
            size: 9,
            color: sym.type === "variable" ? "rgb(236, 72, 153)" : "rgb(6, 182, 212)",
            details: `${t("files.relation.internalSymbol")} ${sym.type}: ${sym.name} (Parsed by Tree-sitter)`,
          })

          links.push({
            id: `file-to-mock-${index}`,
            source: "center-file",
            target: `mock-symbol-${index}`,
            type: "defines",
          })
        })
      }
    }

    // Run simple spring physics force simulation directly inside useMemo
    const iterations = 15
    for (let it = 0; it < iterations; it++) {
      // 1. Repulsion between all nodes
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const n1 = nodes[i]
          const n2 = nodes[j]
          const dx = n2.x - n1.x
          const dy = n2.y - n1.y
          const distSq = dx * dx + dy * dy + 0.1
          const dist = Math.sqrt(distSq)
          const minDist = n1.size + n2.size + 45

          if (dist < minDist) {
            const force = ((minDist - dist) / dist) * 0.15
            const fx = dx * force
            const fy = dy * force

            if (n1.id !== "root" && n1.id !== "center-file") {
              n1.x -= fx
              n1.y -= fy
            }
            if (n2.id !== "root" && n2.id !== "center-file") {
              n2.x += fx
              n2.y += fy
            }
          }
        }
      }

      // 2. Link contraction forces
      links.forEach((link) => {
        const sourceNode = nodes.find((n) => n.id === link.source)
        const targetNode = nodes.find((n) => n.id === link.target)
        if (!sourceNode || !targetNode) return

        const dx = targetNode.x - sourceNode.x
        const dy = targetNode.y - sourceNode.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const desiredDist = link.type === "defines" ? 80 : 130
        const strength = 0.08
        const force = (dist - desiredDist) * strength

        const fx = (dx / dist) * force
        const fy = (dy / dist) * force

        if (sourceNode.id !== "root" && sourceNode.id !== "center-file") {
          sourceNode.x += fx
          sourceNode.y += fy
        }
        if (targetNode.id !== "root" && targetNode.id !== "center-file") {
          targetNode.x -= fx
          targetNode.y -= fy
        }
      })
    }

    return { initialNodes: nodes, initialLinks: links }
  }, [files, symbols, mode, filePath, t])

  const [nodes, setNodes] = useState<GraphNode[]>([])

  useEffect(() => {
    setNodes(initialNodes)
  }, [initialNodes])


  // Filtered nodes based on search
  const filteredNodes = useMemo(() => {
    if (!searchQuery) return nodes
    const q = searchQuery.toLowerCase()
    return nodes.map((n) => {
      const match = n.label.toLowerCase().includes(q)
      return {
        ...n,
        color: match
          ? n.color
          : n.color.replace("rgb", "rgba").replace(")", ", 0.25)"),
      }
    })
  }, [nodes, searchQuery])

  // Mouse handlers for dragging canvas
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.target === canvasRef.current) {
      setIsDraggingCanvas(true)
      dragStart.current = { x: e.clientX - panX, y: e.clientY - panY }
    }
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDraggingCanvas) {
      setPanX(e.clientX - dragStart.current.x)
      setPanY(e.clientY - dragStart.current.y)
    } else if (draggedNodeId) {
      // Drag node
      const rect = canvasRef.current?.getBoundingClientRect()
      if (rect) {
        // Math transform to canvas coordinates
        const x = (e.clientX - rect.left - panX) / zoom
        const y = (e.clientY - rect.top - panY) / zoom

        setNodes((prev) =>
          prev.map((n) => (n.id === draggedNodeId ? { ...n, x, y } : n))
        )
      }
    }
  }

  const handleMouseUp = () => {
    setIsDraggingCanvas(false)
    setDraggedNodeId(null)
  }

  const handleZoom = (factor: number) => {
    setZoom((z) => Math.max(0.4, Math.min(3, z * factor)))
  }

  const handleReset = () => {
    setZoom(1)
    setPanX(0)
    setPanY(0)
    setNodes(initialNodes)
  }

  const getConnectedLinks = (nodeId: string) => {
    return initialLinks.filter(
      (l) => l.source === nodeId || l.target === nodeId
    )
  }

  const isNodeSelectedOrConnected = (nodeId: string) => {
    if (!selectedNodeId) return true
    if (selectedNodeId === nodeId) return true
    return initialLinks.some(
      (l) =>
        (l.source === selectedNodeId && l.target === nodeId) ||
        (l.target === selectedNodeId && l.source === nodeId)
    )
  }

  return (
    <div className="h-full w-full flex flex-col relative select-none bg-zinc-955 text-white font-sans overflow-hidden">
      {/* Top Search & Actions */}
      <div className="absolute top-4 left-4 z-10 flex items-center gap-2">
        <div className="relative">
          <Search className="absolute left-2.5 top-2 h-4 w-4 text-zinc-500" />
          <input
            type="text"
            placeholder={t("sidebar.searchFilesPlaceholder") || "Filter nodes..."}
            className="pl-9 pr-8 py-1.5 h-8 text-xs bg-zinc-900 border border-zinc-800 rounded-lg focus:outline-none focus:border-blue-500/50 w-48 text-zinc-300"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2.5 top-2 text-zinc-500 hover:text-zinc-300 text-xs"
            >
              ×
            </button>
          )}
        </div>
        <div className="flex bg-zinc-900 border border-zinc-800 p-0.5 rounded-lg">
          <button
            onClick={() => handleZoom(1.15)}
            className="p-1 hover:bg-zinc-800 rounded text-zinc-400 hover:text-zinc-200"
            title="Zoom In"
            type="button"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => handleZoom(0.85)}
            className="p-1 hover:bg-zinc-800 rounded text-zinc-400 hover:text-zinc-200"
            title="Zoom Out"
            type="button"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handleReset}
            className="px-1.5 py-0.5 text-[10px] hover:bg-zinc-800 rounded text-zinc-400 hover:text-zinc-200"
            type="button"
          >
            Reset
          </button>
        </div>
      </div>

      <div className="absolute top-4 right-4 z-10 flex flex-col gap-1 items-end bg-zinc-900/80 backdrop-blur-md p-3 border border-zinc-800 rounded-lg text-[10px] text-zinc-400">
        <div className="flex items-center gap-1.5 mb-1.5 font-semibold text-zinc-300 border-b border-zinc-800 pb-1 w-full">
          <Layers className="h-3.5 w-3.5 text-blue-500" />
          <span>{t("files.relation.legendTitle")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-blue-500" />
          <span>{t("files.relation.legendFolder")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500" />
          <span>{t("files.relation.legendFile")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-violet-500" />
          <span>{t("files.relation.legendClass")}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-500" />
          <span>{t("files.relation.legendFunction")}</span>
        </div>
      </div>

      {/* SVG Canvas */}
      <svg
        ref={canvasRef}
        className="w-full h-full cursor-grab active:cursor-grabbing bg-zinc-950/20"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {/* Neon flow filter */}
        <defs>
          <filter id="glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        <g transform={`translate(${panX}, ${panY}) scale(${zoom})`}>
          {/* Link Lines */}
          {initialLinks.map((link) => {
            const sNode = nodes.find((n) => n.id === link.source)
            const tNode = nodes.find((n) => n.id === link.target)
            if (!sNode || !tNode) return null

            const isHighlighted =
              selectedNodeId === null ||
              selectedNodeId === link.source ||
              selectedNodeId === link.target

            // Control line flow styles
            let strokeColor = "rgba(63, 63, 70, 0.4)"
            if (isHighlighted) {
              if (link.type === "imports") strokeColor = "rgba(16, 185, 129, 0.45)"
              else if (link.type === "defines") strokeColor = "rgba(6, 182, 212, 0.45)"
              else strokeColor = "rgba(59, 130, 246, 0.45)"
            }

            const dx = tNode.x - sNode.x
            const dy = tNode.y - sNode.y
            const dist = Math.sqrt(dx * dx + dy * dy)

            // Draw curved link paths
            const mx = (sNode.x + tNode.x) / 2
            const my = (sNode.y + tNode.y) / 2
            const factor = 28 // curve height factor
            const px = -dy / dist * factor
            const py = dx / dist * factor
            const cx = mx + px
            const cy = my + py

            const pathData = `M ${sNode.x} ${sNode.y} Q ${cx} ${cy} ${tNode.x} ${tNode.y}`

            return (
              <g key={link.id}>
                {/* Background thicker glow path */}
                <path
                  d={pathData}
                  fill="none"
                  stroke={strokeColor}
                  strokeWidth={isHighlighted ? 1.5 : 1}
                  className="transition-colors duration-300"
                />

                {/* Animated neon signal dots (on active relations) */}
                {isHighlighted && (link.type === "imports" || link.type === "defines") && (
                  <path
                    d={pathData}
                    fill="none"
                    stroke="url(#glow)"
                    strokeWidth={1}
                    strokeDasharray="4, 16"
                    strokeDashoffset="0"
                    className="animate-flow"
                  >
                    <animate
                      attributeName="stroke-dashoffset"
                      values="100;0"
                      dur="5s"
                      repeatCount="indefinite"
                    />
                  </path>
                )}
              </g>
            )
          })}

          {/* Node Circles */}
          {filteredNodes.map((node) => {
            const isFaded = !isNodeSelectedOrConnected(node.id)
            const nodeOpacity = isFaded ? 0.2 : 1

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                className="cursor-pointer transition-opacity duration-300"
                style={{ opacity: nodeOpacity }}
                onMouseEnter={() => setHoveredNode(node)}
                onMouseLeave={() => setHoveredNode(null)}
                onMouseDown={(e) => {
                  e.stopPropagation()
                  setDraggedNodeId(node.id)
                  setSelectedNodeId(node.id)
                }}
              >
                {/* Glow Ring on hover/select */}
                {(selectedNodeId === node.id || hoveredNode?.id === node.id) && (
                  <circle
                    r={node.size + 6}
                    fill="none"
                    stroke={node.color}
                    strokeWidth={1.5}
                    strokeOpacity={0.4}
                    className="animate-ping"
                    style={{ animationDuration: "3s" }}
                  />
                )}

                <circle
                  r={node.size}
                  fill="rgb(9, 9, 11)"
                  stroke={node.color}
                  strokeWidth={2}
                  filter="url(#glow)"
                />

                {/* Node Icons inside */}
                {node.id === "root" && (
                  <Layers
                    x={-node.size / 2}
                    y={-node.size / 2}
                    width={node.size}
                    height={node.size}
                    className="text-blue-400 shrink-0 pointer-events-none"
                  />
                )}
                {node.type === "folder" && node.id !== "root" && (
                  <Folder
                    x={-node.size / 2}
                    y={-node.size / 2}
                    width={node.size}
                    height={node.size}
                    className="text-amber-500 shrink-0 pointer-events-none"
                  />
                )}
                {node.type === "file" && (
                  <FileCode
                    x={-node.size / 2}
                    y={-node.size / 2}
                    width={node.size}
                    height={node.size}
                    className="text-emerald-500 shrink-0 pointer-events-none"
                  />
                )}
                {(node.type === "class" || node.type === "function" || node.type === "variable") && (
                  <Code
                    x={-node.size / 2}
                    y={-node.size / 2}
                    width={node.size}
                    height={node.size}
                    className="text-cyan-400 shrink-0 pointer-events-none"
                  />
                )}

                {/* Text Label (shown only for folders, selected, or hovered nodes) */}
                {(node.size >= 14 || hoveredNode?.id === node.id || selectedNodeId === node.id) && (
                  <text
                    y={node.size + 14}
                    textAnchor="middle"
                    className="text-[9px] font-medium fill-zinc-300 font-mono drop-shadow-[0_1px_1px_rgba(0,0,0,0.8)] pointer-events-none"
                  >
                    {node.label}
                  </text>
                )}
              </g>
            )
          })}
        </g>
      </svg>

      {/* Floating Info Tooltip */}
      {hoveredNode && (
        <div
          className="absolute bottom-4 left-4 max-w-sm bg-zinc-900/90 backdrop-blur-md p-4 rounded-xl border border-zinc-800 shadow-xl z-20 pointer-events-none animate-fadeIn"
          style={{ animationDuration: "150ms" }}
        >
          <div className="flex items-center gap-2 mb-1.5">
            {hoveredNode.type === "folder" && <Folder className="h-4 w-4 text-amber-500" />}
            {hoveredNode.type === "file" && <FileCode className="h-4 w-4 text-emerald-500" />}
            {(hoveredNode.type === "class" || hoveredNode.type === "function") && (
              <Code className="h-4 w-4 text-cyan-400" />
            )}
            <span className="text-xs font-bold font-mono text-zinc-100">{hoveredNode.label}</span>
          </div>
          <p className="text-[10px] text-zinc-400 font-mono leading-relaxed mb-2 break-all">
            {hoveredNode.details}
          </p>
          <div className="flex gap-3 text-[9px] text-zinc-500 font-semibold border-t border-zinc-800/60 pt-1.5">
            <span>{t("files.relation.degree")}: {getConnectedLinks(hoveredNode.id).length}</span>
            <span>{t("files.relation.scale")}: {hoveredNode.size}px</span>
          </div>
        </div>
      )}

      {/* Interactive Helper Text */}
      <div className="absolute bottom-4 right-4 text-[10px] text-zinc-500/80 bg-zinc-950/40 px-2 py-1 rounded">
        {t("files.relation.interactionHint")}
      </div>

      {/* CSS Animation for Signal Line Glow Flow */}
      <style>{`
        .animate-flow {
          stroke-dasharray: 4, 12;
          animation: dash 5s linear infinite;
        }
        @keyframes dash {
          to {
            stroke-dashoffset: -100;
          }
        }
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-fadeIn {
          animation: fadeIn 0.15s ease-out forwards;
        }
      `}</style>
    </div>
  )
}
