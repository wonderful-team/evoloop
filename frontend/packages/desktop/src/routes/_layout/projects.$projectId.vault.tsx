import { Button } from "@evoloop/shared/components/ui/button"
import { Card, CardContent } from "@evoloop/shared/components/ui/card"
import { Input } from "@evoloop/shared/components/ui/input"
import { Label } from "@evoloop/shared/components/ui/label"
import { Textarea } from "@evoloop/shared/components/ui/textarea"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@evoloop/shared/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@evoloop/shared/components/ui/table"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@evoloop/shared/components/ui/dialog"
import { createFileRoute, useParams } from "@tanstack/react-router"
import { Key, Plus, Trash2, Eye, EyeOff, ShieldAlert, Loader2, Copy, Check, Lock, Edit2, ShieldCheck } from "lucide-react"
import { useState, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { toast } from "sonner"
import { VaultService, type CredentialListItem as Credential } from "@/client"

export const Route = createFileRoute("/_layout/projects/$projectId/vault")({
  component: VaultPage,
})

interface KeyValuePair {
  key: string
  value: string
  show?: boolean
}

function VaultPage() {
  const { projectId } = useParams({ from: "/_layout/projects/$projectId/vault" })
  const { t } = useTranslation()
  const [credentials, setCredentials] = useState<Credential[]>([])
  const [loading, setLoading] = useState(true)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  
  // Form state
  const [identifier, setIdentifier] = useState("")
  const [credType, setCredType] = useState("ssh")
  const [description, setDescription] = useState("")
  const [payloadPairs, setPayloadPairs] = useState<KeyValuePair[]>([])

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
      toast.error(t("common.loadFailed", "Failed to load credentials"))
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
    prefillPayload("ssh")
    setDialogOpen(true)
  }

  const handleOpenEditDialog = (cred: Credential) => {
    setIsEditing(true)
    setIdentifier(cred.identifier)
    setCredType(cred.type)
    setDescription(cred.description || "")
    prefillPayload(cred.type)
    setDialogOpen(true)
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

  const handlePairChange = (index: number, field: "key" | "value", val: string) => {
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
      toast.error(t("vault.errors.identifierRequired", "Identifier is required"))
      return
    }
    const idRegex = /^[\w\-]+$/
    if (!idRegex.test(identifier)) {
      toast.error(t("vault.errors.invalidIdentifier", "Identifier must only contain letters, numbers, underscores, or hyphens"))
      return
    }

    const payloadObj: Record<string, string> = {}
    for (const pair of payloadPairs) {
      if (pair.key.trim()) {
        payloadObj[pair.key.trim()] = pair.value
      }
    }

    if (Object.keys(payloadObj).length === 0) {
      toast.error(t("vault.errors.payloadRequired", "At least one credential field is required"))
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

      toast.success(t("common.saveSuccess", "Credential saved successfully"))
      setDialogOpen(false)
      fetchCredentials()
    } catch (err: any) {
      console.error("Failed to save credential", err)
      toast.error(err.message || t("common.saveFailed", "Failed to save credential"))
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async (identifierToDelete: string) => {
    if (!window.confirm(t("vault.confirmDelete", `Are you sure you want to delete credential '${identifierToDelete}'?`))) {
      return
    }

    try {
      await VaultService.deleteCredential({
        identifier: identifierToDelete,
        projectId: Number(projectId),
      })
      toast.success(t("common.deleteSuccess", "Credential deleted successfully"))
      fetchCredentials()
    } catch (err) {
      console.error("Failed to delete credential", err)
      toast.error(t("common.deleteFailed", "Failed to delete credential"))
    }
  }

  const copyToClipboard = (textToCopy: string) => {
    navigator.clipboard.writeText(textToCopy)
    setCopiedId(textToCopy)
    toast.success(t("common.copied", "Copied to clipboard"))
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
    <div className="h-full w-full overflow-auto p-6 space-y-6 bg-background/50 backdrop-blur-md">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-primary/10 rounded-xl text-primary shadow-inner">
            <Key className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">
              {t("vault.title", "Secure Vault")}
            </h2>
            <p className="text-sm text-muted-foreground mt-0.5">
              {t("vault.description", "Manage encrypted passwords, access tokens, and server keys for this project context.")}
            </p>
          </div>
        </div>
        <Button size="sm" onClick={handleOpenAddDialog} className="shadow-md hover:shadow-lg transition-all">
          <Plus className="h-4 w-4 mr-1" />
          {t("vault.addCredential", "Add Credential")}
        </Button>
      </div>

      {/* Guide Card */}
      <Card className="bg-muted/10 border-dashed border-2 hover:bg-muted/15 transition-all duration-300">
        <CardContent className="pt-6 flex gap-4 items-start">
          <div className="p-3 bg-primary/10 rounded-full text-primary shrink-0">
            <Lock className="h-5 w-5 animate-pulse" />
          </div>
          <div className="space-y-2">
            <h4 className="font-semibold text-sm">
              {t("vault.guide.title", "Zero-Trust Universal Placeholder Substitution")}
            </h4>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {t(
                "vault.guide.text",
                "Credentials added here are encrypted at the backend using AES-256 (Fernet) and never return in cleartext. You can inject these keys into agent commands or code templates securely using the universal placeholder format. When the agent triggers a command, the backend substitutes the value dynamically and automatically censors any raw output."
              )}
            </p>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="text-[10px] uppercase font-bold text-muted-foreground/60 tracking-wider">
                {t("vault.guide.exampleLabel", "Usage example in tools:")}
              </span>
              <code className="text-xs font-mono bg-muted/60 px-2 py-0.5 rounded border border-border shadow-xs">
                {"sshpass -p \"{{vault.identifier.password}}\" ssh user@host"}
              </code>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Credentials Table */}
      {credentials.length > 0 ? (
        <Card className="shadow-sm border border-border overflow-hidden">
          <CardContent className="p-0">
            <Table>
              <TableHeader className="bg-muted/20">
                <TableRow>
                  <TableHead className="w-1/4 py-3">{t("vault.fields.identifier", "Identifier")}</TableHead>
                  <TableHead className="w-1/6 py-3">{t("vault.fields.type", "Type")}</TableHead>
                  <TableHead className="w-1/3 py-3">{t("vault.fields.description", "Description")}</TableHead>
                  <TableHead className="w-1/4 text-right py-3 pr-6">{t("common.actions", "Actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {credentials.map((cred) => (
                  <TableRow key={cred.id} className="hover:bg-muted/30 transition-colors">
                    <TableCell className="font-mono font-medium py-3.5">
                      <div className="flex items-center gap-2">
                        <span className="bg-muted/40 px-2 py-0.5 rounded border border-border/50">{cred.identifier}</span>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="h-6 w-6 opacity-40 hover:opacity-100 transition-opacity"
                          onClick={() => copyToClipboard(`{{vault.${cred.identifier}.key}}`)}
                          title={t("vault.actions.copyPlaceholder", "Copy usage placeholder")}
                        >
                          {copiedId === `{{vault.${cred.identifier}.key}}` ? (
                            <Check className="h-3.5 w-3.5 text-green-500" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className="py-3.5">
                      <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-1 text-xs font-medium text-primary ring-1 ring-inset ring-primary/20 capitalize">
                        {cred.type}
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
                          onClick={() => handleOpenEditDialog(cred)}
                          className="h-8 shadow-xs"
                        >
                          <Edit2 className="h-3.5 w-3.5 mr-1" />
                          {t("common.edit", "Edit")}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDelete(cred.identifier)}
                          className="h-8 text-destructive hover:bg-destructive/10 hover:text-destructive hover:border-destructive/20 shadow-xs"
                        >
                          <Trash2 className="h-3.5 w-3.5 mr-1" />
                          {t("common.delete", "Delete")}
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
            {t("vault.empty.title", "No Secure Credentials")}
          </h3>
          <p className="text-sm text-muted-foreground/60 max-w-sm text-center mt-1">
            {t("vault.empty.description", "Store SSH keys, database passwords, or environment variables to interact with private environments securely.")}
          </p>
          <Button className="mt-4 shadow-sm" size="sm" onClick={handleOpenAddDialog}>
            <Plus className="h-4 w-4 mr-1" />
            {t("vault.addFirstCredential", "Add Your First Credential")}
          </Button>
        </div>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[600px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-xl flex items-center gap-2">
              <Lock className="h-5 w-5 text-primary" />
              {isEditing ? t("vault.dialog.editTitle", "Edit Credential") : t("vault.dialog.addTitle", "Add Credential")}
            </DialogTitle>
            <DialogDescription className="pt-1">
              {isEditing 
                ? t("vault.dialog.editDescription", "Edit credential metadata. Due to secure encryption policies, existing secrets cannot be retrieved; saving will overwrite them.")
                : t("vault.dialog.addDescription", "Add a new credential. The payload keys and values will be securely encrypted.")
              }
            </DialogDescription>
          </DialogHeader>

          {isEditing && (
            <div className="flex gap-3 items-start p-3 bg-amber-500/10 text-amber-600 rounded-lg border border-amber-500/20 text-xs leading-relaxed mb-2">
              <ShieldAlert className="h-4 w-4 shrink-0 mt-0.5 text-amber-500" />
              <div>
                <span className="font-bold">{t("vault.dialog.warningTitle", "Security Warning:")}</span>{" "}
                {t("vault.dialog.warningText", "Editing this credential requires entering all values again. Any fields left blank or omitted will not be preserved.")}
              </div>
            </div>
          )}

          <div className="space-y-4 py-2">
            {/* Identifier */}
            <div className="space-y-1.5">
              <Label htmlFor="identifier" className="text-sm font-semibold flex items-center gap-1.5">
                {t("vault.dialog.fields.identifier", "Credential Identifier")}
                <span className="text-destructive">*</span>
              </Label>
              <Input
                id="identifier"
                placeholder="e.g. customer_a_ssh, github_api_token"
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value)}
                disabled={isEditing || isSaving}
                className="font-mono"
              />
              <p className="text-[10px] text-muted-foreground/60 leading-relaxed">
                {t("vault.dialog.fields.identifierHelp", "Unique string used in code/templates. Letters, numbers, underscores, and hyphens only.")}
              </p>
            </div>

            {/* Type */}
            <div className="space-y-1.5">
              <Label htmlFor="type" className="text-sm font-semibold">
                {t("vault.dialog.fields.type", "Credential Type")}
              </Label>
              <Select value={credType} onValueChange={handleTypeChange} disabled={isSaving}>
                <SelectTrigger id="type" className="w-full">
                  <SelectValue placeholder="Select type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ssh">SSH Server (Host, Port, User, Key/Password)</SelectItem>
                  <SelectItem value="password">Username & Password</SelectItem>
                  <SelectItem value="api_key">API Secret Key / Token</SelectItem>
                  <SelectItem value="env">Environment Variable (.env)</SelectItem>
                  <SelectItem value="custom">Custom Key-Value Dictionary</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Description */}
            <div className="space-y-1.5">
              <Label htmlFor="description" className="text-sm font-semibold">
                {t("vault.dialog.fields.description", "Description")}
              </Label>
              <Textarea
                id="description"
                placeholder={t("vault.dialog.fields.descriptionPlaceholder", "Explain what this credential is for...")}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                disabled={isSaving}
                className="h-16 resize-none"
              />
            </div>

            {/* Key-Value payload pairs */}
            <div className="space-y-3 pt-2">
              <div className="flex justify-between items-center">
                <Label className="text-sm font-semibold flex items-center gap-1.5">
                  {t("vault.dialog.fields.payload", "Credential Fields")}
                  <span className="text-destructive">*</span>
                </Label>
                <Button 
                  type="button" 
                  variant="outline" 
                  size="sm" 
                  onClick={handleAddPair} 
                  disabled={isSaving}
                  className="h-7 text-xs px-2.5"
                >
                  <Plus className="h-3 w-3 mr-1" />
                  {t("vault.dialog.actions.addField", "Add Field")}
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
                          placeholder="Key name"
                          value={pair.key}
                          onChange={(e) => handlePairChange(index, "key", e.target.value)}
                          disabled={isSaving}
                          className="font-mono text-xs h-8"
                        />
                      </div>
                      <div className="flex-1 relative">
                        <Input
                          type={isPassword && !pair.show ? "password" : "text"}
                          placeholder={isPassword ? "Sensitive field value" : "Field value"}
                          value={pair.value}
                          onChange={(e) => handlePairChange(index, "value", e.target.value)}
                          disabled={isSaving}
                          className="text-xs h-8 pr-8"
                        />
                        {isPassword && (
                          <button
                            type="button"
                            className="absolute right-2.5 top-2 text-muted-foreground/50 hover:text-muted-foreground"
                            onClick={() => handleToggleShow(index)}
                            title={pair.show ? "Hide value" : "Show value"}
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
                        size="icon"
                        onClick={() => handleRemovePair(index)}
                        disabled={isSaving}
                        className="h-8 w-8 text-muted-foreground/45 hover:text-destructive hover:bg-destructive/5"
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
              {t("common.cancel", "Cancel")}
            </Button>
            <Button size="sm" onClick={handleSave} disabled={isSaving} className="shadow-md hover:shadow-lg transition-all">
              {isSaving ? (
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
              ) : (
                <ShieldCheck className="h-4 w-4 mr-1" />
              )}
              {t("common.save", "Save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
