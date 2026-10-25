import { useEffect, useState } from "react";
import { useParams } from "@tanstack/react-router";
import { LazyBlockNoteEditor as Preview } from "@/components/editor/lazy-blocknote-editor";
import { LazyMinutesMindMap as MindMap } from "./lazy-minutes-mind-map";
import { FileText, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { PartialBlock } from "@blocknote/core";
import { readLocalShare, saveSharedMinutes } from "../lib/mock-sharing";
import { canEditMinutes } from "../lib/minutes-state";
import type { Workspace } from "@/apis/meetings";

export function SharedMinutesPage() {
  const { token } = useParams({ from: "/shared/meetings/$token" });
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [canEdit, setCanEdit] = useState(false);
  const [content, setContent] = useState("");
  const [blocks, setBlocks] = useState<PartialBlock[] | undefined>();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    let alive = true;
    setWorkspace(null);
    setError(null);
    void readLocalShare(token)
      .then(({ share, draft }) => {
        if (!alive) return;
        setWorkspace(draft);
        setContent(draft.minutes?.content ?? "");
        setBlocks(draft.minutes?.blocks);
        setCanEdit(share.permission === "edit" && canEditMinutes(draft.meeting));
      })
      .catch((cause) => {
        if (alive) setError(cause instanceof Error ? cause.message : "读取分享失败");
      });
    return () => {
      alive = false;
    };
  }, [token]);
  async function save() {
    if (!canEdit || busy) return;
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await saveSharedMinutes(token, content, blocks);
      setSaved(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="flex h-dvh flex-col gap-5 bg-background px-6 py-6 md:px-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs tracking-widest text-muted-foreground">SHARED MEETING NOTES</p>
          <h1 className="text-xl font-semibold">{workspace?.meeting.title ?? "分享的会议纪要"}</h1>
          <p className="mt-2 text-xs text-muted-foreground">
            {canEdit ? "可编辑" : "可阅读"} · 本地演示链接，仅在创建链接的浏览器中有效
          </p>
        </div>
        {canEdit && (
          <Button disabled={busy} onClick={() => void save()}>
            <Save className="size-4" />
            {busy ? "正在保存…" : "保存修改"}
          </Button>
        )}
      </header>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {saved && (
        <p role="status" className="text-xs text-emerald-700">
          修改已保存，会议原文同步更新。
        </p>
      )}
      {!workspace && !error && <p role="status">正在读取分享内容…</p>}
      {workspace && (
        <div className="grid min-h-0 flex-1 gap-4 overflow-auto lg:grid-cols-2">
          <section className="flex min-h-80 flex-col overflow-hidden rounded-xl border">
            <h2 className="flex items-center gap-2 border-b px-5 py-3 text-sm font-medium">
              <FileText className="size-4" />
              会议纪要
            </h2>
            {canEdit ? (
              <div className="min-h-0 flex-1 overflow-auto" aria-label="共享会议纪要富文本编辑器">
                <Preview
                  initialContent={blocks}
                  markdown={blocks ? undefined : content}
                  editable={!busy}
                  className="p-5"
                  onDocumentChange={({ blocks: nextBlocks, markdown }) => {
                    setContent(markdown);
                    setBlocks(nextBlocks);
                    setSaved(false);
                  }}
                />
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-auto">
                <Preview
                  initialContent={blocks}
                  markdown={blocks ? undefined : content}
                  editable={false}
                  className="p-5"
                />
              </div>
            )}
          </section>
          <section className="flex min-h-96 flex-col rounded-xl border lg:min-h-0">
            <h2 className="border-b px-5 py-3 text-sm font-medium">重点思维导图</h2>
            <div className="min-h-0 flex-1">
              <MindMap title={workspace.meeting.title} content={content} />
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
