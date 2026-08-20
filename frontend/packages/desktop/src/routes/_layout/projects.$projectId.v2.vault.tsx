import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent } from "@evoloop/shared/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
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
import { createFileRoute, useParams } from "@tanstack/react-router"
import {
  Check,
  Copy,
  Edit2,
  Eye,
  EyeOff,
  Key,
  Loader2,
  Lock,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { type CredentialListItem as Credential, VaultService } from "@/client"

export const Route = createFileRoute("/_layout/projects/$projectId/v2/vault")({
  component: VaultPage,
})

interface KeyValuePair {
  key: string
  value: string
  show?: boolean
}

function VaultPage() {
  const { projectId } = useParams({
    from: "/_layout/projects/$projectId/v2/vault",
  })
  const { t } = useTranslation()
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [loading, setLoading] = useState(true)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)

  const [identifier, setIdentifier] = useState("")
  const [credType, setCredType] = useState("ssh")
  const [description, setDescription] = useState("")
  const [payloadPairs, setPayloadPairs] = useState<KeyValuePair[]>([])
  const [originalKeys, setOriginalKeys] = useState<string[]>([])

  const [viewOpen, setViewOpen] = useState(false)
  const [viewCredential, setViewCredential] = useState<Credential | null>(null)
  const [viewPayload, setViewPayload] = useState<Record<string, string>>({})
  const [viewLoading, setViewLoading] = useState(false)
  const [viewRevealed, setViewRevealed] = useState<Record<string, boolean>>({})

  const fetchCredentials = async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const data = await VaultService.listCredentials({
        projectId: Number(projectId),
      })
      setCredentials(data)
    } catch (err) {
      console.error("Failed to load credentials", err)
      toast.error(t("common.loadFailed"))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchCredentials()
  }, [projectId])

  const prefillPayload = (type: string) => {
    if (type === "ssh") {
      setPayloadPairs([
        { key: "host", value: "" },
        { key: "port", value: "22" },
        { key: "username", value: "" },
        { key: "password", value: "", show: false },
        { key: "private_key", value: "", show: false },
      ])
    } else if (type === "password") {
      setPayloadPairs([{ key: "password", value: "", show: false }])
    } else if (type === "api_key") {
      setPayloadPairs([{ key: "api_key", value: "", show: false }])
    } else if (type === "env") {
      setPayloadPairs([{ key: "value", value: "" }])
    } else {
      setPayloadPairs([{ key: "", value: "" }])
    }
  }

  const handleOpenAddDialog = () => {
    setIsEditing(false)
    setIdentifier("")
    setCredType("ssh")
    setDescription("")
    setOriginalKeys([])
    prefillPayload("ssh")
    setDialogOpen(true)
  }

  const handleOpenEditDialog = async (cred: Credential) => {
    setIsEditing(true)
    setIdentifier(cred.identifier)
    setCredType(cred.type)
    setDescription(cred.description || "")
    setPayloadPairs([])
    setDialogOpen(true)
    try {
      const res = (await VaultService.listCredentialFields({
        identifier: cred.identifier,
        projectId: Number(projectId),
      })) as { fields?: string[] }
      const fields = res?.fields ?? []
      setOriginalKeys(fields)
      setPayloadPairs(fields.map((key) => ({ key, value: "", show: false })))
    } catch (err) {
      console.error("Failed to load credential fields", err)
      toast.error(t("common.loadFailed"))
    }
  }

  const handleOpenViewDialog = async (cred: Credential) => {
    setViewCredential(cred)
    setViewPayload({})
    setViewRevealed({})
    setViewOpen(true)
    setViewLoading(true)
    try {
      const res = (await VaultService.getCredentialPayload({
        identifier: cred.identifier,
        projectId: Number(projectId),
      })) as { payload?: Record<string, string> }
      const payload = res?.payload ?? {}
      setViewPayload(payload)
      setViewRevealed(
        Object.fromEntries(
          Object.keys(payload).map((key) => [
            key,
            /pass|key|secret|token/i.test(key),
          ]),
        ),
      )
    } catch (err) {
      console.error("Failed to load credential payload", err)
      toast.error(t("common.loadFailed"))
    } finally {
      setViewLoading(false)
    }
  }

  const handleTypeChange = (value: string) => {
    setCredType(value)
    prefillPayload(value)
  }

  const handleAddPair = () => {
    setPayloadPairs([...payloadPairs, { key: "", value: "", show: false }])
  }

  const handleRemovePair = (index: number) => {
    const newPairs = [...payloadPairs]
    newPairs.splice(index, 1)
    setPayloadPairs(newPairs)
  }

  const handlePairChange = (
    index: number,
    field: "key" | "value",
    val: string,
  ) => {
    const newPairs = [...payloadPairs]
    newPairs[index][field] = val
    setPayloadPairs(newPairs)
  }

  const handleToggleShow = (index: number) => {
    const newPairs = [...payloadPairs]
    newPairs[index].show = !newPairs[index].show
    setPayloadPairs(newPairs)
  }

  const handleSave = async () => {
    if (!identifier.trim()) {
      toast.error(t("vault.errors.identifierRequired"))
      return
    }
    const idRegex = /^[\w-]+$/
    if (!idRegex.test(identifier)) {
      toast.error(t("vault.errors.invalidIdentifier"))
      return
    }

    const payloadObj: Record<string, string | null> = {}
    for (const pair of payloadPairs) {
      if (pair.key.trim()) {
        payloadObj[pair.key.trim()] = pair.value
      }
    }

    if (isEditing) {
      for (const key of originalKeys) {
        if (!(key in payloadObj)) {
          payloadObj[key] = null
        }
      }
    }

    if (Object.keys(payloadObj).length === 0) {
      toast.error(t("vault.errors.payloadRequired"))
      return
    }

    setIsSaving(true)
    try {
      await VaultService.addCredential({
        requestBody: {
          identifier,
          type: credType,
          project_id: Number(projectId),
          description: description || null,
          payload: payloadObj,
        },
      })

      toast.success(t("common.saveSuccess"))
      setDialogOpen(false)
      fetchCredentials()
    } catch (err: any) {
      console.error("Failed to save credential", err)
      toast.error(err.message || t("common.saveFailed"))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async (identifierToDelete: string) => {
    if (
      !window.confirm(
        t("vault.confirmDelete", { identifier: identifierToDelete }),
      )
    ) {
      return
    }

    try {
      await VaultService.deleteCredential({
        identifier: identifierToDelete,
        projectId: Number(projectId),
      })
      toast.success(t("common.deleteSuccess"))
      fetchCredentials()
    } catch (err) {
      console.error("Failed to delete credential", err)
      toast.error(t("common.deleteFailed"))
    }
  }

  const copyToClipboard = (textToCopy: string) => {
    navigator.clipboard.writeText(textToCopy)
    setCopiedId(textToCopy)
    toast.success(t("common.copied"))
    setTimeout(() => setCopiedId(null), 2000)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full overflow-hidden">
      <div className="flex-1 overflow-auto p-6 space-y-6 max-w-6xl mx-auto w-full">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-primary/10 rounded-xl text-primary shrink-0">
              <Key className="h-6 w-6" />
            </div>
            <div>
              <h2 className="text-2xl font-bold tracking-tight">
                {t("vault.title")}
              </h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                {t("vault.description")}
              </p>
            </div>
          </div>
          <Button
            size="sm"
            onClick={handleOpenAddDialog}
            className="shadow-sm gap-1.5"
          >
            <Plus className="h-4 w-4" />
            <span>{t("vault.addCredential")}</span>
          </Button>
        </div>

        <Card className="bg-muted/10 border-dashed border-2 hover:bg-muted/15 transition-all">
          <CardContent className="pt-6 flex gap-4 items-start">
            <div className="p-3 bg-primary/10 rounded-full text-primary shrink-0">
              <Lock className="h-5 w-5 animate-pulse" />
            </div>
            <div className="space-y-2">
              <h4 className="font-semibold text-sm">
                {t("vault.guide.title")}
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                {t("vault.guide.text")}
              </p>
              <div className="flex flex-wrap items-center gap-2 pt-1">
                <span className="text-[10px] uppercase font-bold text-muted-foreground/60 tracking-wider">
                  {t("vault.guide.exampleLabel")}
                </span>
                <code className="text-xs font-mono bg-muted/60 px-2 py-0.5 rounded border border-border">
                  {'sshpass -p "{{vault.identifier.password}}" ssh user@host'}
                </code>
              </div>
            </div>
          </CardContent>
        </Card>

        {credentials.length > 0 ? (
          <Card className="shadow-sm border border-border overflow-hidden">
            <CardContent className="p-0">
              <Table>
                <TableHeader className="bg-muted/20">
                  <TableRow>
                    <TableHead className="w-1/4 py-3">
                      {t("vault.fields.identifier")}
                    </TableHead>
                    <TableHead className="w-1/6 py-3">
                      {t("vault.fields.type")}
                    </TableHead>
                    <TableHead className="w-1/3 py-3">
                      {t("vault.fields.description")}
                    </TableHead>
                    <TableHead className="w-1/4 text-right py-3 pr-6">
                      {t("common.actions")}
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {credentials.map((cred) => (
                    <TableRow
                      key={cred.id}
                      className="hover:bg-muted/30 transition-colors"
                    >
                      <TableCell className="font-mono font-medium py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="bg-muted/40 px-2 py-0.5 rounded border border-border/50">
                            {cred.identifier}
                          </span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 opacity-40 hover:opacity-100 transition-opacity"
                            onClick={() =>
                              copyToClipboard(
                                `{{vault.${cred.identifier}.key}}`,
                              )
                            }
                            title={t("vault.actions.copyPlaceholder")}
                          >
                            {copiedId === `{{vault.${cred.identifier}.key}}` ? (
                              <Check className="h-3.5 w-3.5 text-emerald-500" />
                            ) : (
                              <Copy className="h-3.5 w-3.5" />
                            )}
                          </Button>
                        </div>
                      </TableCell>
                      <TableCell className="py-3.5">
                        <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20 capitalize">
                          {t(`vault.types.${cred.type}`)}
                        </span>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm max-w-xs truncate py-3.5">
                        {cred.description || "-"}
                      </TableCell>
                      <TableCell className="text-right py-3.5 pr-6">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenViewDialog(cred)}
                            className="h-8 shadow-xs"
                            title={t("vault.actions.view")}
                          >
                            <Eye className="h-3.5 w-3.5 mr-1" />
                            {t("vault.actions.view")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleOpenEditDialog(cred)}
                            className="h-8 shadow-xs"
                          >
                            <Edit2 className="h-3.5 w-3.5 mr-1" />
                            {t("common.edit")}
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => handleDelete(cred.identifier)}
                            className="h-8 text-destructive hover:bg-destructive/10 hover:text-destructive hover:border-destructive/20 shadow-xs"
                          >
                            <Trash2 className="h-3.5 w-3.5 mr-1" />
                            {t("common.delete")}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ) : (
          <div className="flex flex-col items-center justify-center py-24 border border-dashed rounded-xl bg-muted/5">
            <Key className="h-12 w-12 text-muted-foreground/30 mb-4 animate-pulse" />
            <h3 className="font-semibold text-lg text-muted-foreground">
              {t("vault.empty.title")}
            </h3>
            <p className="text-sm text-muted-foreground/60 max-w-sm text-center mt-1">
              {t("vault.empty.description")}
            </p>
            <Button
              className="mt-4 shadow-sm"
              size="sm"
              onClick={handleOpenAddDialog}
            >
              <Plus className="h-4 w-4 mr-1" />
              {t("vault.addFirstCredential")}
            </Button>
          </div>
        )}

        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogContent className="sm:max-w-[600px] max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-xl flex items-center gap-2">
                <Lock className="h-5 w-5 text-primary" />
                {isEditing
                  ? t("vault.dialog.editTitle")
                  : t("vault.dialog.addTitle")}
              </DialogTitle>
              <DialogDescription className="pt-1">
                {isEditing
                  ? t("vault.dialog.editDescription")
                  : t("vault.dialog.addDescription")}
              </DialogDescription>
            </DialogHeader>

            {isEditing && (
              <div className="flex gap-3 items-start p-3 bg-amber-500/10 text-amber-600 rounded-lg border border-amber-500/20 text-xs leading-relaxed mb-2">
                <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-amber-500" />
                <div>
                  <span className="font-bold">
                    {t("vault.dialog.warningTitle")}
                  </span>{" "}
                  {t("vault.dialog.warningText")}
                </div>
              </div>
            )}

            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label
                  htmlFor="identifier"
                  className="text-sm font-semibold flex items-center gap-1.5"
                >
                  {t("vault.dialog.fields.identifier")}
                  <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="identifier"
                  placeholder={t("vault.dialog.identifierPlaceholder")}
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  disabled={isEditing || isSaving}
                  className="font-mono"
                />
                <p className="text-[10px] text-muted-foreground/60 leading-relaxed">
                  {t("vault.dialog.fields.identifierHelp")}
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="type" className="text-sm font-semibold">
                  {t("vault.dialog.fields.type")}
                </Label>
                <Select
                  value={credType}
                  onValueChange={handleTypeChange}
                  disabled={isSaving}
                >
                  <SelectTrigger id="type" className="w-full">
                    <SelectValue
                      placeholder={t("vault.dialog.typePlaceholder")}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ssh">{t("vault.types.ssh")}</SelectItem>
                    <SelectItem value="password">
                      {t("vault.types.password")}
                    </SelectItem>
                    <SelectItem value="api_key">
                      {t("vault.types.api_key")}
                    </SelectItem>
                    <SelectItem value="env">{t("vault.types.env")}</SelectItem>
                    <SelectItem value="custom">
                      {t("vault.types.custom")}
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="description" className="text-sm font-semibold">
                  {t("vault.dialog.fields.description")}
                </Label>
                <Textarea
                  id="description"
                  placeholder={t("vault.dialog.fields.descriptionPlaceholder")}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  disabled={isSaving}
                  className="h-16 resize-none"
                />
              </div>

              <div className="space-y-3 pt-2">
                <div className="flex justify-between items-center">
                  <Label className="text-sm font-semibold flex items-center gap-1.5">
                    {t("vault.dialog.fields.payload")}
                    <span className="text-destructive">*</span>
                  </Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleAddPair}
                    disabled={isSaving}
                    className="h-8 text-xs px-2.5"
                  >
                    <Plus className="h-3.5 w-3.5 mr-1" />
                    {t("vault.dialog.actions.addField")}
                  </Button>
                </div>

                <div className="space-y-3 max-h-[30vh] overflow-y-auto pr-1 border rounded-lg p-3 bg-muted/5">
                  {payloadPairs.map((pair, index) => {
                    const isPassword =
                      pair.key.toLowerCase().includes("pass") ||
                      pair.key.toLowerCase().includes("key") ||
                      pair.key.toLowerCase().includes("secret") ||
                      pair.key.toLowerCase().includes("token")

                    return (
                      <div key={index} className="flex gap-2 items-start group">
                        <div className="w-1/3">
                          <Input
                            placeholder={t(
                              "vault.dialog.fields.keyPlaceholder",
                            )}
                            value={pair.key}
                            onChange={(e) =>
                              handlePairChange(index, "key", e.target.value)
                            }
                            disabled={isSaving}
                            className="font-mono text-xs h-8"
                          />
                        </div>
                        <div className="flex-1 relative">
                          <Input
                            type={
                              isPassword && !pair.show ? "password" : "text"
                            }
                            placeholder={
                              isPassword
                                ? t(
                                    "vault.dialog.fields.sensitiveValuePlaceholder",
                                  )
                                : t("vault.dialog.fields.valuePlaceholder")
                            }
                            value={pair.value}
                            onChange={(e) =>
                              handlePairChange(index, "value", e.target.value)
                            }
                            disabled={isSaving}
                            className="text-xs h-8 pr-8"
                          />
                          {isPassword && (
                            <button
                              type="button"
                              className="absolute right-2.5 top-2 text-muted-foreground/50 hover:text-muted-foreground"
                              onClick={() => handleToggleShow(index)}
                              title={
                                pair.show
                                  ? t("vault.dialog.fields.hideValue")
                                  : t("vault.dialog.fields.showValue")
                              }
                            >
                              {pair.show ? (
                                <EyeOff className="h-3.5 w-3.5" />
                              ) : (
                                <Eye className="h-3.5 w-3.5" />
                              )}
                            </button>
                          )}
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemovePair(index)}
                          disabled={isSaving}
                          className="h-8 w-8 p-0 text-muted-foreground/45 hover:text-destructive hover:bg-destructive/5"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    )
                  })}
                </div>
              </div>
            </div>

            <DialogFooter className="pt-4 border-t gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDialogOpen(false)}
                disabled={isSaving}
              >
                {t("common.cancel")}
              </Button>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={isSaving}
                className="shadow-md hover:shadow-lg transition-all"
              >
                {isSaving ? (
                  <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                ) : (
                  <ShieldCheck className="h-4 w-4 mr-1" />
                )}
                {t("common.save")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        <Dialog open={viewOpen} onOpenChange={setViewOpen}>
          <DialogContent className="sm:max-w-[560px] max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="text-xl flex items-center gap-2">
                <Eye className="h-5 w-5 text-primary" />
                {t("vault.view.title")}
                {viewCredential && (
                  <span className="font-mono text-sm text-muted-foreground font-normal">
                    {viewCredential.identifier}
                  </span>
                )}
              </DialogTitle>
              <DialogDescription className="pt-1">
                {t("vault.view.description")}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3 py-2">
              {viewLoading ? (
                <div className="flex items-center justify-center py-10">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : (
                <div className="space-y-2 border rounded-lg p-3 bg-muted/5">
                  {Object.entries(viewPayload).map(([key, value]) => {
                    const hidden = viewRevealed[key]
                    return (
                      <div key={key} className="flex gap-2 items-center">
                        <span className="w-1/3 font-mono text-xs text-muted-foreground truncate">
                          {key}
                        </span>
                        <span className="flex-1 font-mono text-xs px-2 py-1.5 bg-background rounded border border-border/60 min-w-0">
                          {hidden ? "••••••" : value || "-"}
                        </span>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground/60 hover:text-muted-foreground"
                          onClick={() =>
                            setViewRevealed((prev) => ({
                              ...prev,
                              [key]: !prev[key],
                            }))
                          }
                          title={
                            hidden
                              ? t("vault.view.showValue")
                              : t("vault.view.hideValue")
                          }
                        >
                          {hidden ? (
                            <Eye className="h-3.5 w-3.5" />
                          ) : (
                            <EyeOff className="h-3.5 w-3.5" />
                          )}
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground/60 hover:text-muted-foreground"
                          onClick={() => copyToClipboard(value)}
                          title={t("vault.view.copyValue")}
                        >
                          {copiedId === value ? (
                            <Check className="h-3.5 w-3.5 text-emerald-500" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </div>
                    )
                  })}
                  {Object.keys(viewPayload).length === 0 && !viewLoading && (
                    <p className="text-sm text-muted-foreground py-6 text-center">
                      -
                    </p>
                  )}
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      </div>
    </div>
  )
}
