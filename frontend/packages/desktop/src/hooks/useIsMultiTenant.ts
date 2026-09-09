import { useQuery } from "@tanstack/react-query"
import { SystemService } from "@/client"

/**
 * Whether the current deployment is multi-tenant (hosted/cloud) mode.
 *
 * The backend exposes MULTI_TENANT_MODE in /system/config. The frontend uses
 * this to hide onboarding/welcome/setup-wizard UI that only makes sense in
 * single-user (desktop/local) mode.
 */
export function useIsMultiTenant(): boolean {
  const { data } = useQuery({
    queryKey: ["systemConfig"],
    queryFn: () => SystemService.getSystemConfig(),
    staleTime: 1000 * 60 * 5,
  })

  if (!data || !Array.isArray(data)) return false
  const entry = (data as Array<{ key: string; value: string }>).find(
    (item) => item.key === "MULTI_TENANT_MODE",
  )
  return entry?.value === "true"
}