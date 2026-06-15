import { Button } from "@evoloop/shared/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@evoloop/shared/components/ui/dialog"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@evoloop/shared/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@evoloop/shared/components/ui/table"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { useParams } from "@tanstack/react-router"
import { Clock, Loader2, Plus, RefreshCw } from "lucide-react"
import type React from "react"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { ProjectModulesService } from "@/client"
import type { TimesheetEntry } from "@/types/timesheet"

export const TimesheetList: React.FC = () => {
  const { t } = useTranslation()
  const { projectId } = useParams({ from: "/_layout/projects/$projectId" })

  const [entries, setEntries] = useState<TimesheetEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Form State
  const [hours, setHours] = useState("")
  const [description, setDescription] = useState("")
  const [workType, setWorkType] = useState("development")

  const fetchTimesheets = useCallback(async () => {
    if (!projectId) return
    setIsLoading(true)
    try {
      // Backend identifies user via Cookie Session.
      const res: any = await ProjectModulesService.getTimesheetList({
        projectId: parseInt(projectId, 10),
        page: 1,
        pageSize: 50,
      })
      if (res?.list) {
        setEntries(res.list)
      } else if (Array.isArray(res)) {
        setEntries(res)
      } else {
        setEntries([])
      }
    } catch (error) {
      console.error(error)
      toast.error(t("projects.timesheet.errors.loadFailed"))
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchTimesheets()
  }, [fetchTimesheets])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!projectId) return

    if (!hours || !description) {
      toast.error(t("projects.timesheet.errors.fillRequired"))
      return
    }

    setIsSubmitting(true)
    try {
      // Backend identifies user via Cookie Session.
      await ProjectModulesService.quickAddTimesheet({
        requestBody: {
          project_id: parseInt(projectId, 10),
          hours: parseFloat(hours),
          description: description,
          work_type: workType,
        },
      })
      toast.success(t("projects.timesheet.success.added"))
      setIsDialogOpen(false)
      // Reset form
      setHours("")
      setDescription("")
      fetchTimesheets()
    } catch (error) {
      console.error(error)
      toast.error(t("projects.timesheet.errors.addFailed"))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="h-full w-full overflow-auto p-6 space-y-6">
      <div className="space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-xl font-semibold tracking-tight">
            {t("projects.timesheet.title")}
          </h2>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={fetchTimesheets}
              disabled={isLoading}
            >
              <RefreshCw
                className={`w-4 h-4 mr-2 ${isLoading ? "animate-spin" : ""}`}
              />
              {t("projects.timesheet.refresh")}
            </Button>

            <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
              <DialogTrigger asChild>
                <Button size="sm">
                  <Plus className="w-4 h-4 mr-2" />
                  {t("projects.timesheet.logTime")}
                </Button>
              </DialogTrigger>
              <DialogContent className="sm:max-w-[425px]">
                <form onSubmit={handleSubmit}>
                  <DialogHeader>
                    <DialogTitle>
                      {t("projects.timesheet.dialog.title")}
                    </DialogTitle>
                    <DialogDescription>
                      {t("projects.timesheet.dialog.desc")}
                    </DialogDescription>
                  </DialogHeader>
                  <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-4 items-center gap-4">
                      <Label htmlFor="type" className="text-right">
                        {t("projects.timesheet.dialog.type")}
                      </Label>
                      <Select value={workType} onValueChange={setWorkType}>
                        <SelectTrigger className="col-span-3">
                          <SelectValue
                            placeholder={t(
                              "projects.timesheet.dialog.selectType",
                            )}
                          />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="development">
                            {t("projects.timesheet.types.development")}
                          </SelectItem>
                          <SelectItem value="design">
                            {t("projects.timesheet.types.design")}
                          </SelectItem>
                          <SelectItem value="testing">
                            {t("projects.timesheet.types.testing")}
                          </SelectItem>
                          <SelectItem value="meeting">
                            {t("projects.timesheet.types.meeting")}
                          </SelectItem>
                          <SelectItem value="other">
                            {t("projects.timesheet.types.other")}
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="grid grid-cols-4 items-center gap-4">
                      <Label htmlFor="hours" className="text-right">
                        {t("projects.timesheet.dialog.hours")}
                      </Label>
                      <div className="col-span-3 relative">
                        <Input
                          id="hours"
                          type="number"
                          step="0.1"
                          value={hours}
                          onChange={(e) => setHours(e.target.value)}
                          placeholder={t(
                            "projects.timesheet.dialog.hoursPlaceholder",
                          )}
                          className="pl-9"
                        />
                        <Clock className="w-4 h-4 absolute left-3 top-3 text-muted-foreground" />
                      </div>
                    </div>
                    <div className="grid grid-cols-4 items-center gap-4">
                      <Label htmlFor="desc" className="text-right">
                        {t("projects.timesheet.dialog.description")}
                      </Label>
                      <Textarea
                        id="desc"
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder={t(
                          "projects.timesheet.dialog.descPlaceholder",
                        )}
                        className="col-span-3"
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button type="submit" disabled={isSubmitting}>
                      {isSubmitting && (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      )}
                      {t("projects.timesheet.dialog.save")}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        <div className="rounded-md">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[100px]">
                  {t("projects.timesheet.table.date")}
                </TableHead>
                <TableHead>{t("projects.timesheet.table.member")}</TableHead>
                <TableHead>{t("projects.timesheet.table.type")}</TableHead>
                <TableHead>{t("projects.timesheet.table.desc")}</TableHead>
                <TableHead className="text-right">
                  {t("projects.timesheet.table.hours")}
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && entries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} className="h-24 text-center">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ) : entries.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={5}
                    className="h-24 text-center text-muted-foreground"
                  >
                    {t("projects.timesheet.table.noLogs")}
                  </TableCell>
                </TableRow>
              ) : (
                entries.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="font-medium text-nowrap">
                      {entry.work_date}
                      {entry.created_at && (
                        <div className="text-xs text-muted-foreground">
                          {new Date(entry.created_at).toLocaleDateString()}
                        </div>
                      )}
                    </TableCell>
                    <TableCell>
                      {entry.member_name || entry.member_id}
                    </TableCell>
                    <TableCell className="capitalize">
                      {entry.work_type}
                    </TableCell>
                    <TableCell
                      className="max-w-[400px] truncate"
                      title={entry.description}
                    >
                      {entry.description}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {entry.hours}h
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}
