import { Input } from "@evoloop/shared/components/ui/input"
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@evoloop/shared/components/ui/resizable"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"
import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { FileCode, Loader2, Search, X } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { FilesService } from "@/client"
import { FilePreview } from "@/components/Files/FilePreview"
import { FileTree } from "@/components/Files/FileTree"

export const Route = createFileRoute("/_layout/projects/$projectId/files")({
  component: FilesPage,
})

function FilesPage() {
  const { projectId } = Route.useParams()
  const [selectedFile, setSelectedFile] = useState<{
    path: string
    name: string
  } | null>(null)
  const { t } = useTranslation()

  const [searchQuery, setSearchQuery] = useState("")
  const [isSearching, setIsSearching] = useState(false)
  const {
    data: searchResults,
    isLoading: isLoadingSearch,
    refetch: searchFiles,
  } = useQuery({
    queryKey: ["fileSearch", projectId, searchQuery],
    queryFn: async () => {
      if (!projectId || !searchQuery) return []
      const res = await FilesService.searchFiles({
        projectId: Number(projectId),
        q: searchQuery,
      })
      return res as any[]
    },
    enabled: false,
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchQuery.trim().length >= 2) {
      setIsSearching(true)
      searchFiles()
    }
  }

  const clearSearch = () => {
    setSearchQuery("")
    setIsSearching(false)
  }

  return (
    <ResizablePanelGroup direction="horizontal" className="h-full w-full">
      <ResizablePanel
        defaultSize={20}
        minSize={15}
        maxSize={40}
        className="bg-muted/5 flex flex-col min-w-[200px]"
      >
        <div className="p-2 border-b">
          <form onSubmit={handleSearch} className="relative">
            <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              className="pl-8 h-8 text-xs pr-7"
              placeholder={t("sidebar.searchFilesPlaceholder")}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={clearSearch}
                className="absolute right-2 top-2.5 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </form>
        </div>

        <div className="flex-1 overflow-hidden flex flex-col">
          {!isSearching ? (
            <div className="flex-1 overflow-auto py-2">
              <FileTree
                projectId={Number(projectId)}
                onSelectFile={(node) =>
                  setSelectedFile({ path: node.path, name: node.name })
                }
              />
            </div>
          ) : (
            <div className="flex-1 overflow-hidden flex flex-col">
              <div className="px-3 py-2 text-[10px] font-semibold text-muted-foreground uppercase tracking-wider flex justify-between items-center">
                <span>{t("files.searchResults")}</span>
                {isLoadingSearch && (
                  <Loader2 className="h-3 w-3 animate-spin" />
                )}
              </div>
              <ScrollArea className="flex-1">
                <div className="p-2 space-y-1">
                  {searchResults?.map((result, i) => (
                    <div
                      key={i}
                      className="p-2 rounded border border-transparent hover:border-border hover:bg-muted/50 cursor-pointer text-xs group transition-all"
                      onClick={() =>
                        setSelectedFile({
                          path: result.file,
                          name: result.file.split("/").pop() || "",
                        })
                      }
                    >
                      <div className="flex items-center gap-1.5 text-primary font-medium mb-1">
                        <FileCode className="h-3.5 w-3.5" />
                        <span className="truncate" title={result.file}>
                          {result.file}:{result.line}
                        </span>
                      </div>
                      <div className="text-muted-foreground font-mono truncate opacity-70 group-hover:opacity-100">
                        {result.content}
                      </div>
                    </div>
                  ))}
                  {isSearching &&
                    !isLoadingSearch &&
                    searchResults?.length === 0 && (
                      <div className="text-center py-8 text-muted-foreground text-xs italic">
                        {t("files.noMatches")}
                      </div>
                    )}
                </div>
              </ScrollArea>
            </div>
          )}
        </div>
      </ResizablePanel>

      <ResizableHandle withHandle />

      <ResizablePanel defaultSize={80}>
        <div className="h-full flex flex-col bg-background min-w-0">
          {selectedFile ? (
            <FilePreview projectId={Number(projectId)} file={selectedFile} />
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground/50 bg-muted/5">
              <FileCode className="h-16 w-16 mb-4 opacity-10" />
              <p>{t("files.selectFileToView")}</p>
            </div>
          )}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}
