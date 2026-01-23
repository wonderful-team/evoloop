import { useQuery } from "@tanstack/react-query"
import { useNavigate, useSearch } from "@tanstack/react-router"
import {
  AlertTriangle,
  Cpu,
  FolderOpen,
  Monitor,
  Search,
  Terminal,
  User,
  X,
} from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import {
  DevicesService,
  ProjectsService,
  LogsService,
} from "@/mobile/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function SearchScreen() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const searchParams = useSearch({ strict: false }) as any
  // Initial filters from URL or default
  const [keyword, setKeyword] = useState("")
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(
    searchParams.deviceId ? Number(searchParams.deviceId) : null,
  )
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(
    searchParams.projectId ? Number(searchParams.projectId) : null,
  )
  const [results, setResults] = useState<any[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [history, setHistory] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem("search_history")
      return saved ? JSON.parse(saved) : []
    } catch {
      return []
    }
  })

  const addToHistory = (term: string) => {
    if (!term.trim()) return
    const newHistory = [term, ...history.filter((h) => h !== term)].slice(0, 10)
    setHistory(newHistory)
    localStorage.setItem("search_history", JSON.stringify(newHistory))
  }

  const clearHistory = () => {
    setHistory([])
    localStorage.removeItem("search_history")
  }

  // Fetch Devices for filter matching/name display
  const { data: devices } = useQuery({
    queryKey: ["evoloop", "devices"],
    queryFn: async () => {
      const res = await DevicesService.getDevices()
      return res.code >= 0 ? res.data : []
    },
  })

  // Fetch Projects for filter matching
  const { data: projectsData } = useQuery({
    queryKey: ["evoloop", "projects"],
    queryFn: async () => {
      const res = await ProjectsService.getProjects()
      return res.code >= 0 ? res.data : { list: [] }
    },
  })
  const projects = (projectsData as any)?.list || []

  const performSearch = async (term: string) => {
    if (!term.trim()) return
    setIsSearching(true)
    addToHistory(term)
    try {
      const res = await LogsService.searchLogs({
        q: term,
        project_id: selectedProjectId || undefined,
        device_id: selectedDeviceId || undefined,
      })
      const list = res.code >= 0 ? res.data : []
      setResults(
        list.map((item: any) => ({
          ...item,
          create_time: item.create_time || item.timestamp || Date.now() / 1000,
        })),
      )
    } catch (e: any) {
      toast.error(`${t("search.failedPrefix")}${e.message}`)
    } finally {
      setIsSearching(false)
    }
  }

  const handleSearch = () => {
    performSearch(keyword)
  }

  const handleResultClick = (log: any) => {
    if (!log.thread_id && !log.log_id) return
    navigate({
      to: `/chat/${log.thread_id || log.log_id}` as any,
      search: { highlight: log.log_id },
    } as any)
  }

  // Get names for chips
  const currentDeviceName = devices?.find(
    (d) => d.device_id === selectedDeviceId,
  )?.device_name
  const currentProjectName = projects?.find(
    (p: any) => p.project_id === selectedProjectId,
  )?.project_name

  return (
    <div className="flex flex-col h-screen bg-background">
      {/* Header */}
      <div className="bg-background border-b px-4 py-3 flex flex-col gap-3 sticky top-0 z-10 pt-safe-top pt-10">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              autoFocus
              placeholder={t("search.placeholder")}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              className="pl-9 h-9"
            />
            {keyword && (
              <button
                onClick={() => setKeyword("")}
                className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <Button variant="ghost" onClick={() => navigate({ to: ".." })}>
            {t("search.cancel")}
          </Button>
        </div>

        {/* Filters */}
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
          {/* Device Filter Chip */}
          {selectedDeviceId ? (
            <Badge
              variant="secondary"
              className="gap-1 flex items-center pr-1 h-7 shrink-0"
            >
              <Monitor className="w-3 h-3" />
              <span className="truncate max-w-[100px]">
                {currentDeviceName ||
                  t("search.deviceLabel", { id: selectedDeviceId })}
              </span>
              <button
                onClick={() => setSelectedDeviceId(null)}
                className="ml-1 hover:bg-muted-foreground/20 rounded-full p-0.5"
              >
                <X className="w-3 h-3" />
              </button>
            </Badge>
          ) : (
            <div className="text-xs text-muted-foreground px-2 py-1 bg-muted rounded-full shrink-0">
              {t("search.allDevices")}
            </div>
          )}

          {/* Project Filter Chip */}
          {selectedProjectId ? (
            <Badge
              variant="secondary"
              className="gap-1 flex items-center pr-1 h-7 shrink-0"
            >
              <FolderOpen className="w-3 h-3" />
              <span className="truncate max-w-[100px]">
                {currentProjectName ||
                  t("search.projectLabel", { id: selectedProjectId })}
              </span>
              <button
                onClick={() => setSelectedProjectId(null)}
                className="ml-1 hover:bg-muted-foreground/20 rounded-full p-0.5"
              >
                <X className="w-3 h-3" />
              </button>
            </Badge>
          ) : (
            <div className="text-xs text-muted-foreground px-2 py-1 bg-muted rounded-full shrink-0">
              {t("search.allProjects")}
            </div>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-4 py-2">
        {/* History */}
        {!keyword &&
          !isSearching &&
          results.length === 0 &&
          history.length > 0 && (
            <div className="mt-4">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-medium text-muted-foreground">
                  {t("search.recent")}
                </h3>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-xs text-muted-foreground"
                  onClick={clearHistory}
                >
                  {t("search.clear")}
                </Button>
              </div>
              <div className="flex flex-wrap gap-2">
                {history.map((term, i) => (
                  <Badge
                    key={i}
                    variant="outline"
                    className="cursor-pointer hover:bg-muted py-1 px-2 font-normal"
                    onClick={() => {
                      setKeyword(term)
                      performSearch(term)
                    }}
                  >
                    {term}
                  </Badge>
                ))}
              </div>
            </div>
          )}

        {results.length === 0 && !isSearching && keyword && (
          <div className="text-center text-muted-foreground mt-8 text-sm">
            {t("search.noResults")}
          </div>
        )}
        {isSearching && (
          <div className="text-center text-muted-foreground mt-8 text-sm">
            {t("search.searching")}
          </div>
        )}

        <div className="space-y-4 pt-2">
          {results.map((log) => (
            <div
              key={log.log_id}
              className="flex flex-col gap-2 p-3 rounded-lg border bg-card hover:bg-muted/50 transition-colors cursor-pointer"
              onClick={() => handleResultClick(log)}
            >
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  {/* Type Icon */}
                  {log.type === "user" && <User className="w-3 h-3" />}
                  {log.type === "thought" && <Cpu className="w-3 h-3" />}
                  {log.type === "tool" && <Terminal className="w-3 h-3" />}
                  {log.type === "error" && (
                    <AlertTriangle className="w-3 h-3 text-destructive" />
                  )}

                  <span>
                    {new Date(log.create_time * 1000).toLocaleString(
                      t("common.locale") || "en-US",
                      {
                        month: "2-digit",
                        day: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        hour12: false,
                      },
                    )}
                  </span>
                </div>
                <span className="px-1.5 py-0.5 bg-muted rounded text-[10px]">
                  {t("search.logLabel", { id: log.log_id })}
                </span>
              </div>
              <div className="text-sm line-clamp-3 break-all font-mono">
                {typeof log.content === "string"
                  ? log.content
                  : JSON.stringify(log.content)}
              </div>
              {/* Context Info (if mixed scope) */}
              {(!selectedDeviceId || !selectedProjectId) && (
                <div className="flex gap-2 mt-1">
                  {!selectedDeviceId && (
                    <Badge
                      variant="outline"
                      className="text-[10px] h-5 px-1 font-normal text-muted-foreground"
                    >
                      {devices?.find((d) => d.device_id === log.device_id)
                        ?.device_name ||
                        t("search.deviceLabel", { id: log.device_id })}
                    </Badge>
                  )}
                  {!selectedProjectId && log.project_id > 0 && (
                    <Badge
                      variant="outline"
                      className="text-[10px] h-5 px-1 font-normal text-muted-foreground"
                    >
                      {projects?.find(
                        (p: any) => p.project_id === log.project_id,
                      )?.project_name ||
                        t("search.projectLabel", { id: log.project_id })}
                    </Badge>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
