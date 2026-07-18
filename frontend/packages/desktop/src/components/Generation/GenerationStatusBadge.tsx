import { Badge } from "@evoloop/shared/components/ui/badge"

const statusVariant: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending: "outline",
  running: "default",
  completed: "secondary",
  failed: "destructive",
}

const statusLabel: Record<string, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
}

interface GenerationStatusBadgeProps {
  status: string
}

export function GenerationStatusBadge({ status }: GenerationStatusBadgeProps) {
  const label = statusLabel[status] ?? status
  const variant = statusVariant[status] ?? "outline"
  return <Badge variant={variant}>{label}</Badge>
}
