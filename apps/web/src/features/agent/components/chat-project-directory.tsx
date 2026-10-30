import { useState } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { FolderOpen, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { changeThreadProject, useAgentStore } from "@/stores/agent";
import { useAgentApprovalStore } from "@/stores/agent/agent-approvals";
import { addLocalProject } from "@/stores/agent/agent-projects";
import { useProjects } from "../hooks/use-projects";

/** 当前会话的项目目录，选取本地目录必须经过 Electron 原生选择器。 */
export function ChatProjectDirectory() {
  const aui = useAui();
  const id = useAuiState((s) => s.threadListItem.remoteId);
  const detail = useAgentStore((s) => (id ? s.details[id] : undefined));
  const sending = useAgentStore((s) => (id ? s.sending[id] : false));
  const waiting = useAgentApprovalStore((s) =>
    id ? s.entries[id]?.items.some((row) => row.actionable) : false,
  );
  const { items, loading } = useProjects();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const project = items.find((row) => row.id === detail?.thread.project_id);
  const disabled =
    busy || sending || waiting || detail?.messages.some((row) => row.status === "waiting_approval");
  async function choose(projectId: string | null, add = false) {
    if (disabled) return;
    setBusy(true);
    setError(null);
    try {
      if (add) {
        const added = await addLocalProject();
        if (!added) return;
        projectId = added.id;
      }
      let threadId = id;
      if (!threadId) threadId = (await aui.threadListItem.initialize()).remoteId;
      await changeThreadProject(threadId, projectId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "工作目录选择失败。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mb-2 px-1">
      <div className="flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
        <FolderOpen className="mr-1 size-3.5 shrink-0" />
        <Select
          value={detail?.thread.project_id ?? "none"}
          disabled={!!disabled || loading}
          onValueChange={(value) => {
            if (typeof value === "string") void choose(value === "none" ? null : value);
          }}
        >
          <SelectTrigger
            aria-label="选择工作目录"
            title={project?.path ?? "不选择项目工作目录"}
            className="h-7 w-auto max-w-72 gap-1 border-0 bg-transparent px-1.5 text-xs shadow-none"
          >
            <SelectValue>
              {(value) => items.find((row) => row.id === value)?.name ?? "不选择工作目录"}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="none">不选择工作目录</SelectItem>
            {items.map((row) => (
              <SelectItem key={row.id} value={row.id}>
                {row.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="ghost"
          size="icon-xs"
          aria-label="添加文件夹作为工作目录"
          title={
            window.desktop?.selectProjectDirectory ? "添加本地文件夹" : "请在桌面端添加本地文件夹"
          }
          disabled={!!disabled || !window.desktop?.selectProjectDirectory}
          onClick={() => void choose(null, true)}
        >
          {busy ? <Loader2 className="size-3.5 animate-spin" /> : <Plus className="size-3.5" />}
        </Button>
      </div>
      {error && (
        <p role="alert" className="mt-1 text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
