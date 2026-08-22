import { Button } from "@evoloop/shared/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@evoloop/shared/components/ui/card";
import { Checkbox } from "@evoloop/shared/components/ui/checkbox";
import { Input } from "@evoloop/shared/components/ui/input";
import { Label } from "@evoloop/shared/components/ui/label";
import { Textarea } from "@evoloop/shared/components/ui/textarea";
import { AlertCircle, Headset, Loader2, Play, Square } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "sonner";
import { ProjectsService } from "@/client/sdk.gen";

function generatePromptId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function defaultPrompt(): BusinessPollPrompt {
  const next = new Date();
  next.setHours(next.getHours() + 1);
  return {
    id: generatePromptId(),
    prompt: "",
    next_run_at: next.toISOString(),
    interval_minutes: 60,
    enabled: true,
  };
}

function isoToLocalInput(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function localInputToIso(value: string): string {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toISOString();
}

interface DutyChannelCfg {
  enabled?: boolean;
}

interface BusinessPollPrompt {
  id: string;
  prompt: string;
  next_run_at: string;
  interval_minutes: number;
  enabled: boolean;
}

interface ProjectDutyConfig {
  enabled: boolean;
  channels?: Record<string, DutyChannelCfg>;
  business_poll_prompts?: BusinessPollPrompt[];
}

/**
 * 项目值守页（项目侧边栏"值守"tab）。
 * 本项目是否参与值守 + 该项目企微参数。开启触发后端校验，失败回滚并展示原因。
 */
export function ProjectDutyCard({ projectId }: { projectId: number }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [config, setConfig] = useState<ProjectDutyConfig>({ enabled: false });
  const [businessPollPrompts, setBusinessPollPrompts] = useState<
    BusinessPollPrompt[]
  >([]);
  const [errors, setErrors] = useState<string[]>([]);
  const fetchConfig = useCallback(async () => {
    setLoading(true);
    try {
      const res = await ProjectsService.getProjectDuty({ projectId });
      const duty = (res ?? {}) as Record<string, unknown>;
      const channels = (duty.channels ?? {}) as Record<string, DutyChannelCfg>;
      setConfig({
        enabled: Boolean(duty.enabled),
        channels,
        business_poll_prompts: (duty.business_poll_prompts ??
          []) as BusinessPollPrompt[],
      });
      setBusinessPollPrompts(
        (duty.business_poll_prompts ?? []) as BusinessPollPrompt[],
      );
      setErrors([]);
    } catch {
      toast.error(t("projects.duty.loadError"));
    } finally {
      setLoading(false);
    }
  }, [projectId, t]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleToggle = async (enabled: boolean) => {
    setSaving(true);
    setErrors([]);
    try {
      const channels = config.channels ?? {};
      await ProjectsService.updateProjectDuty({
        projectId,
        requestBody: { enabled, channels },
      });
      setConfig({ enabled, channels });
      toast.success(
        enabled ? t("projects.duty.enabled") : t("projects.duty.disabled"),
      );
    } catch (e) {
      // 后端校验失败（ApiError.body = {detail: {message, errors}}），enabled 已回滚 false
      const body = (e as { body?: unknown })?.body as
        | { detail?: { message?: string; errors?: string[] } }
        | undefined;
      const reason = body?.detail?.errors ?? [];
      setErrors(reason);
      setConfig((prev) => ({ ...prev, enabled: false }));
      if (reason.length === 0 && !body?.detail?.message) {
        toast.error(t("projects.duty.startFailed"));
      }
    } finally {
      setSaving(false);
    }
  };

  const updatePrompt = (
    id: string,
    patch: Partial<Omit<BusinessPollPrompt, "id">>,
  ) => {
    setBusinessPollPrompts((prev) =>
      prev.map((p) => (p.id === id ? { ...p, ...patch } : p)),
    );
  };

  const removePrompt = (id: string) => {
    setBusinessPollPrompts((prev) => prev.filter((p) => p.id !== id));
  };

  const addPrompt = () => {
    setBusinessPollPrompts((prev) => [...prev, defaultPrompt()]);
  };

  const saveBusinessPoll = async () => {
    setSaving(true);
    setErrors([]);
    const prompts = businessPollPrompts.map((p) => ({
      id: p.id,
      prompt: p.prompt,
      next_run_at: p.next_run_at,
      interval_minutes: p.interval_minutes,
      enabled: p.enabled,
    }));
    try {
      await ProjectsService.updateProjectDuty({
        projectId,
        requestBody: {
          business_poll_prompts: prompts,
        },
      });
      setConfig((prev) => ({
        ...prev,
        business_poll_prompts: prompts,
      }));
      toast.success(t("projects.duty.businessSaved"));
    } catch {
      toast.error(t("projects.duty.saveError"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      {/* 状态与主操作 */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-medium">
            <Headset className="h-5 w-5 text-primary" />
            {t("projects.duty.title")}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* 值守状态横幅 */}

          <div
            className={
              config.enabled
                ? "flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 p-4"
                : "flex items-center justify-between rounded-lg border border-muted bg-muted/40 p-4"
            }
          >
            <div className="flex items-center gap-3">
              <div
                className={
                  config.enabled
                    ? "flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100"
                    : "flex h-10 w-10 items-center justify-center rounded-full bg-muted"
                }
              >
                {config.enabled ? (
                  <Square className="h-5 w-5 text-emerald-600" />
                ) : (
                  <Play className="h-5 w-5 text-muted-foreground" />
                )}
              </div>
              <div>
                <p
                  className={
                    config.enabled
                      ? "text-sm font-semibold text-emerald-700"
                      : "text-sm font-semibold text-muted-foreground"
                  }
                >
                  {config.enabled
                    ? t("projects.duty.active")
                    : t("projects.duty.inactive")}
                </p>
                <p className="text-xs text-muted-foreground">
                  {config.enabled
                    ? t("projects.duty.runningDesc")
                    : t("projects.duty.stoppedDesc")}
                </p>
              </div>
            </div>
            {config.enabled ? (
              <Button
                variant="outline"
                size="sm"
                className="gap-2 border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                disabled={saving}
                onClick={() => handleToggle(false)}
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
                {t("projects.duty.stopDuty")}
              </Button>
            ) : (
              <Button
                size="sm"
                className="gap-2"
                disabled={saving}
                onClick={() => handleToggle(true)}
              >
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" />
                )}
                {t("projects.duty.startDuty")}
              </Button>
            )}
          </div>

          {/* 启动失败原因 */}
          {errors.length > 0 && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-destructive">
                <AlertCircle className="h-4 w-4" />
                {t("projects.duty.failedTitle")}
              </div>
              <ul className="mt-2 space-y-1">
                {errors.map((reason, i) => (
                  <li key={i} className="text-xs text-muted-foreground">
                    • {reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="space-y-6">
        <div className="space-y-6">
          {/* 业务巡检（运营线）：Agent 主动巡检商城业务，独立于客服轮巡节奏 */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base font-medium">
                {t("projects.duty.businessTitle")}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-xs text-muted-foreground">
                {t("projects.duty.businessDesc")}
              </p>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-sm font-medium">
                    {t("projects.duty.businessPollTasksLabel")}
                  </Label>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={saving}
                    onClick={addPrompt}
                  >
                    {t("projects.duty.addBusinessPollTask")}
                  </Button>
                </div>
                {businessPollPrompts.length === 0 && (
                  <p className="text-xs text-muted-foreground">
                    {t("projects.duty.noBusinessPollTasks")}
                  </p>
                )}
                {businessPollPrompts.map((p) => (
                  <div key={p.id} className="space-y-2 rounded-lg border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Checkbox
                          checked={p.enabled}
                          onCheckedChange={(checked) =>
                            updatePrompt(p.id, { enabled: Boolean(checked) })
                          }
                          disabled={saving}
                        />
                        <span className="text-xs text-muted-foreground">
                          {p.enabled
                            ? t("projects.duty.taskEnabled")
                            : t("projects.duty.taskDisabled")}
                        </span>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-7 text-xs text-destructive"
                        disabled={saving}
                        onClick={() => removePrompt(p.id)}
                      >
                        {t("projects.duty.deleteTask")}
                      </Button>
                    </div>
                    <Textarea
                      value={p.prompt}
                      onChange={(e) =>
                        updatePrompt(p.id, { prompt: e.target.value })
                      }
                      placeholder={t(
                        "projects.duty.businessPollTaskPlaceholder",
                      )}
                      rows={3}
                      className="transition-colors focus:border-primary"
                      disabled={saving}
                    />
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div className="space-y-1">
                        <Label className="text-xs">
                          {t("projects.duty.taskNextRunAt")}
                        </Label>
                        <Input
                          type="datetime-local"
                          value={isoToLocalInput(p.next_run_at)}
                          onChange={(e) =>
                            updatePrompt(p.id, {
                              next_run_at: localInputToIso(e.target.value),
                            })
                          }
                          className="h-9"
                          disabled={saving}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">
                          {t("projects.duty.taskInterval")}
                        </Label>
                        <Input
                          type="number"
                          min={1}
                          max={1440}
                          step={1}
                          value={p.interval_minutes}
                          onChange={(e) => {
                            const n = Number(e.target.value);
                            if (Number.isInteger(n) && n >= 1) {
                              updatePrompt(p.id, { interval_minutes: n });
                            }
                          }}
                          className="h-9"
                          disabled={saving}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex justify-end">
                <Button
                  variant="outline"
                  disabled={saving}
                  onClick={saveBusinessPoll}
                >
                  {saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    t("projects.duty.businessSaved")
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
