import type { AgentRuntimeConfig, AgentConfig } from "@/interfaces/agent";
import { useEffect, useState } from "react";
import { Loader2, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { Textarea } from "@/components/ui/textarea";
import { getAccessToken } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogFooter,
  DialogTitle,
} from "@/components/ui/dialog";
import { getAgentConfig, updateAgentConfig } from "@/apis/agents";

/** 打开时读取当前设备的配置，不在聊天初始化时请求。 */
export function AgentConfigDialog({ agent }: { agent: AgentConfig }) {
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState<AgentRuntimeConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setConfig(null);
    setError(null);
    setSaveError(null);
    void (async () => {
      try {
        const result = await getAgentConfig(agent.code, controller.signal);
        if (!controller.signal.aborted) {
          setConfig(result);
          setDraft(result.prompt);
        }
      } catch (cause: unknown) {
        if (!controller.signal.aborted)
          setError(cause instanceof Error ? cause.message : "配置读取失败");
      }
    })();
    return () => controller.abort();
  }, [agent.code, open, revision]);
  async function save() {
    if (!config || saving) return;
    const token = getAccessToken();
    setSaving(true);
    setSaveError(null);
    try {
      const result = await updateAgentConfig(agent.code, draft, config.prompt);
      if (getAccessToken() !== token) return;
      setConfig(result);
      setDraft(result.prompt);
      toast.success("提示词已保存，下次对话生效");
    } catch (cause) {
      if (getAccessToken() === token)
        setSaveError(cause instanceof Error ? cause.message : "提示词保存失败，请重试。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={`查看${agent.name}配置`}
        onClick={() => setOpen(true)}
      >
        <Settings2 className="size-4" />
      </Button>
      <Dialog
        open={open}
        onOpenChange={(value) => {
          if (!saving) setOpen(value);
        }}
      >
        <DialogContent className="flex max-h-[85vh] flex-col sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{agent.name}配置</DialogTitle>
            <DialogDescription>当前设备的 Agent 配置 · {agent.code}/AGENT.md</DialogDescription>
          </DialogHeader>
          <div className="min-h-0 overflow-y-auto">
            {error ? (
              <div className="grid gap-3 py-6">
                <p role="alert" className="text-sm text-destructive">
                  {error}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  className="justify-self-start"
                  onClick={() => setRevision((value) => value + 1)}
                >
                  重新加载
                </Button>
              </div>
            ) : config ? (
              <section>
                <label
                  htmlFor={`agent-prompt-${agent.code}`}
                  className="mb-3 block text-sm font-medium"
                >
                  提示词
                </label>
                <Textarea
                  id={`agent-prompt-${agent.code}`}
                  value={draft}
                  disabled={saving}
                  onChange={(event) => setDraft(event.target.value)}
                  className="field-sizing-fixed h-[45vh] min-h-64 resize-y font-mono text-sm leading-7"
                />
                {saveError && (
                  <div className="mt-3 grid gap-2">
                    <p role="alert" className="text-sm text-destructive">
                      {saveError}
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="justify-self-start"
                      disabled={saving}
                      onClick={() => setRevision((value) => value + 1)}
                    >
                      重新加载
                    </Button>
                  </div>
                )}
              </section>
            ) : (
              <p
                role="status"
                className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground"
              >
                <Loader2 className="size-4 animate-spin" />
                正在读取配置…
              </p>
            )}
          </div>
          <DialogFooter className="items-center sm:justify-between">
            <p className="text-xs text-muted-foreground">保存到本机 AGENT.md，下次对话生效。</p>
            <Button
              disabled={!config || saving || !draft.trim() || draft.trim() === config.prompt}
              onClick={() => void save()}
            >
              {saving && <Loader2 className="size-4 animate-spin" />}
              {saving ? "保存中…" : "保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
