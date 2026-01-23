import { useQuery } from "@tanstack/react-query"
import { FileText, Loader2, Search } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { FilesService } from "@/client"
import { Button } from "@evoloop/shared/components/ui/button"
import { Input } from "@evoloop/shared/components/ui/input"
import { ScrollArea } from "@evoloop/shared/components/ui/scroll-area"

interface FileSearchResult {
  file: string
  line: number
  content: string
}

interface KnowledgeTabProps {
  projectId?: number
}

export function KnowledgeTab({ projectId }: KnowledgeTabProps) {
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState("")

  // 3. Knowledge Search
  const {
    data: searchResults,
    isLoading: isLoadingSearch,
    refetch: searchFiles,
  } = useQuery({
    queryKey: ["fileSearch", projectId, searchQuery],
    queryFn: async () => {
      if (
        typeof projectId !== "number" ||
        Number.isNaN(projectId) ||
        !searchQuery
      )
        return []
      const res = await FilesService.searchFiles({ projectId, q: searchQuery })
      return res as any as FileSearchResult[] // Cast strict unknown from SDK to known search result shape
    },
    enabled: false, // Trigger manually
  })

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchQuery.trim().length >= 2) {
      searchFiles()
    }
  }

  if (!projectId) return null

  return (
    <div className="h-full m-0 flex flex-col">
      <div className="p-2 border-b bg-muted/20 space-y-2">
        <form onSubmit={handleSearch} className="flex gap-2">
          <Input
            className="h-8 text-xs"
            placeholder={t("chat.context.searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <Button
            size="icon"
            variant="secondary"
            className="h-8 w-8"
            type="submit"
          >
            <Search className="h-4 w-4" />
          </Button>
        </form>
      </div>
      <ScrollArea className="flex-1 p-3">
        {isLoadingSearch ? (
          <div className="flex justify-center p-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : searchResults && searchResults.length > 0 ? (
          <div className="space-y-2">
            {searchResults.map((result, i) => (
              <div
                key={i}
                className="border rounded p-2 text-xs bg-card hover:bg-accent/50 transition-colors cursor-pointer group"
              >
                <div className="font-medium flex items-center gap-1.5 text-primary mb-1">
                  <FileText className="h-3 w-3" />
                  {result.file}:{result.line}
                </div>
                <div className="font-mono text-muted-foreground truncate opacity-80 group-hover:opacity-100">
                  {result.content}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center text-xs text-muted-foreground py-8">
            {searchResults
              ? t("chat.context.noMatches")
              : t("chat.context.searchPrompt")}
          </div>
        )}
      </ScrollArea>
    </div>
  )
}
