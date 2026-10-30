import { useState } from "react";
import { Button } from "@/components/ui/button";
import { exportMarkdown } from "@/apis/meetings";
import { publish } from "@/stores/meeting";
import { isPending, replaceFromServer, type Draft } from "../lib/workspace-storage";

export function SaveStatus({
  draft,
  retry,
  editable = true,
}: {
  draft: Draft & { localSaved: boolean };
  retry: () => Promise<unknown>;
  editable?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    setBusy(true);
    setError(null);
    try {
      await retry();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function reload() {
    setBusy(true);
    setError(null);
    try {
      // 导出包含临时输入和全部片段的恢复副本，再载入 服务器版本。
      exportMarkdown(
        draft.meeting.title + "-本地恢复副本",
        `${draft.minutes?.content ?? ""}\n\n## 原始记录\n${draft.segments.map((row) => `${row.speaker ?? "未署名"}：${row.text}`).join("\n\n")}\n\n## 未确认输入\n${draft.temporary.speaker}：${draft.temporary.text}`,
      );
      const fresh = await replaceFromServer(draft, true);
      publish({ ...fresh, version: draft.version + 1 });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "载入失败");
    } finally {
      setBusy(false);
    }
  }
  const pending = isPending(draft);
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" role="status">
      <span className={draft.error || error ? "text-destructive" : "text-muted-foreground"}>
        {draft.error
          ? "保存失败"
          : !draft.localSaved || pending
            ? "保存中…"
            : draft.temporary.text
              ? "识别中 · 临时文字尚未确认"
              : "已保存"}
      </span>
      {(pending || draft.error || !draft.localSaved) && (
        <Button size="xs" variant="outline" onClick={() => void run()} disabled={busy}>
          {busy ? "保存中…" : "重试保存"}
        </Button>
      )}
      {(draft.error || error) && <span className="text-destructive">{error ?? draft.error}</span>}
      {editable && (draft.error?.includes("其他页面") || error?.includes("其他页面")) && (
        <Button size="xs" variant="outline" disabled={busy} onClick={() => void reload()}>
          下载本地副本并重新加载
        </Button>
      )}
    </div>
  );
}
