import { lazy, Suspense, useEffect, useRef, useState, type MutableRefObject } from "react";
import * as Y from "yjs";
import { Copy, History, Share2, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  getRecord,
  shareRecord,
  listRecordVersions,
  getRecordVersion,
  checkpointRecord,
  restoreRecord,
  type RecordDocument,
  type RecordVersion,
} from "@/apis/meeting-records";
import { useAuthStore } from "@/stores/auth";
import { RecordCollaborators } from "./record-collaborators";
import { decodeState, RecordProvider, type RecordStatus } from "../lib/record-provider";
const Editor = lazy(() =>
  import("./record-editor").then((module) => ({ default: module.RecordEditor })),
);
export type RecordFlush = MutableRefObject<(() => Promise<void>) | null>;

export function RecordWorkspace({
  meetingId,
  shareToken,
  initial,
  flushRef,
  disabled = false,
  onContentChange,
}: {
  meetingId: string;
  shareToken?: string;
  initial?: RecordDocument;
  flushRef?: RecordFlush;
  disabled?: boolean;
  onContentChange?: (content: string) => void;
}) {
  const [document, setDocument] = useState(initial ?? null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const ownerId = useAuthStore((state) => state.user?.id);
  useEffect(() => {
    let alive = true;
    void getRecord(meetingId, shareToken)
      .then((value) => {
        if (alive) {
          setDocument(value);
          setError("");
        }
      })
      .catch((cause: Error) => {
        if (alive) setError(cause.message);
      });
    return () => {
      alive = false;
    };
  }, [meetingId, shareToken, reload, ownerId]);
  if (error)
    return (
      <div role="alert" className="p-5 text-sm text-destructive">
        {error}
        <Button variant="ghost" onClick={() => setReload((value) => value + 1)}>
          重试
        </Button>
      </div>
    );
  if (!document) return <p className="p-5 text-sm text-muted-foreground">正在读取协作纪要…</p>;
  return (
    <RecordSession
      key={`${meetingId}:${ownerId}:${document.epoch}`}
      document={document}
      shareToken={shareToken}
      flushRef={flushRef}
      disabled={disabled}
      reset={setDocument}
      onContentChange={onContentChange}
    />
  );
}

function RecordSession({
  document,
  shareToken,
  flushRef,
  disabled,
  reset,
  onContentChange,
}: {
  document: RecordDocument;
  shareToken?: string;
  flushRef?: RecordFlush;
  disabled: boolean;
  reset: (document: RecordDocument) => void;
  onContentChange?: (content: string) => void;
}) {
  // 同一协作世代只初始化一次连接，详情重取不替换正在编辑的文档。
  const initialDocument = useRef(document).current;
  const [provider, setProvider] = useState<RecordProvider | null>(null);
  const [status, setStatus] = useState<RecordStatus>({
    document,
    connected: false,
    pending: false,
    saving: false,
    saveError: null,
    error: null,
  });
  const [history, setHistory] = useState(false);
  const [link, setLink] = useState("");
  const [shareError, setShareError] = useState("");
  const [shareBusy, setShareBusy] = useState(false);
  const username = useAuthStore((state) => state.user?.username ?? "同事");
  useEffect(() => {
    const connection = new RecordProvider(initialDocument, shareToken, setStatus, reset);
    setProvider(connection);
    if (flushRef) flushRef.current = () => connection.flush();
    return () => {
      if (flushRef) flushRef.current = null;
      connection.destroy();
    };
  }, [initialDocument, shareToken, flushRef, reset]);
  const current = status.document;
  useEffect(() => {
    onContentChange?.(current.content);
  }, [current.content, onContentChange]);
  async function openShare() {
    setShareBusy(true);
    setShareError("");
    try {
      const result = await shareRecord(current.meeting_id);
      setLink(new URL(`/shared/meeting-records/${result.token}`, window.location.origin).href);
    } catch (cause) {
      setShareError((cause as Error).message);
    } finally {
      setShareBusy(false);
    }
  }
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
        <span role="status" className="text-xs text-muted-foreground">
          {status.saveError
            ? "保存失败"
            : status.error
              ? "同步失败"
              : !status.connected
                ? "连接中 · 等待同步"
                : status.pending || status.saving
                  ? "保存中…"
                  : `最近保存于 ${new Date(current.saved_at ?? current.updated_at).toLocaleString()}`}{" "}
          · {current.editable ? "支持协同编辑" : "只读"}
        </span>
        <div className="flex flex-wrap items-center gap-3">
          <RecordCollaborators provider={provider} connected={status.connected} />
          <Button variant="ghost" size="sm" onClick={() => setHistory(true)}>
            <History className="size-4" />
            版本历史
          </Button>
          {current.owner && (
            <Popover
              onOpenChange={(open) => {
                if (open) void openShare();
              }}
            >
              <PopoverTrigger
                render={
                  <Button variant="outline" size="sm">
                    <Share2 className="size-4" />
                    分享
                  </Button>
                }
              />
              <PopoverContent align="end" className="w-96 max-w-[calc(100vw-2rem)]">
                <p className="text-sm font-medium">分享会议纪要</p>
                <p className="my-2 text-xs text-muted-foreground">
                  同事登录后，持链接可协同编辑纪要。归档后锁定编辑。
                </p>
                {shareBusy && !link ? (
                  <p className="text-xs">正在读取链接…</p>
                ) : link ? (
                  <div className="flex gap-2">
                    <Input
                      aria-label="纪要协同链接"
                      readOnly
                      value={link}
                      onFocus={(event) => event.target.select()}
                    />
                    <Button
                      aria-label="复制纪要协同链接"
                      size="icon"
                      variant="outline"
                      onClick={() =>
                        void navigator.clipboard
                          .writeText(link)
                          .then(() => toast.success("链接已复制"))
                          .catch(() => setShareError("请手动复制链接"))
                      }
                    >
                      <Copy className="size-4" />
                    </Button>
                  </div>
                ) : null}
                {shareError && (
                  <p role="alert" className="mt-2 text-xs text-destructive">
                    {shareError}
                  </p>
                )}
              </PopoverContent>
            </Popover>
          )}
        </div>
      </div>
      {status.saveError && (
        <div role="alert" className="flex items-center gap-2 px-5 py-2 text-sm text-destructive">
          <span>{status.saveError}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              void provider?.flush().catch(() => {});
            }}
          >
            重试保存
          </Button>
        </div>
      )}
      {status.error && (
        <p role="alert" className="px-5 py-2 text-sm text-destructive">
          {status.error} 请保留页面中的未同步内容。
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto" aria-label="会议纪要协同富文本编辑器">
        <Suspense fallback={<p className="p-5 text-sm">正在加载编辑器…</p>}>
          {provider && (
            <Editor
              key={provider.doc.guid}
              doc={provider.doc}
              provider={provider}
              username={username}
              editable={current.editable && !disabled && !status.error}
            />
          )}
        </Suspense>
      </div>
      {provider && (
        <VersionHistory
          open={history}
          close={() => setHistory(false)}
          status={status}
          provider={provider}
          shareToken={shareToken}
          reset={reset}
        />
      )}
    </div>
  );
}

function VersionHistory({
  open,
  close,
  status,
  provider,
  shareToken,
  reset,
}: {
  open: boolean;
  close: () => void;
  status: RecordStatus;
  provider: RecordProvider;
  shareToken?: string;
  reset: (document: RecordDocument) => void;
}) {
  const [versions, setVersions] = useState<RecordVersion[]>([]);
  const [selected, setSelected] = useState<RecordVersion | null>(null);
  const [preview, setPreview] = useState<Y.Doc | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const requestSequence = useRef({ value: 0 });
  const id = status.document.meeting_id;
  useEffect(() => {
    if (!open) return;
    let alive = true;
    const sequence = requestSequence.current;
    void listRecordVersions(id, shareToken)
      .then((rows) => {
        if (alive) setVersions(rows);
      })
      .catch((cause: Error) => {
        if (alive) setError(cause.message);
      });
    return () => {
      alive = false;
      sequence.value++;
    };
  }, [open, id, shareToken]);
  useEffect(() => () => preview?.destroy(), [preview]);
  async function select(version: RecordVersion) {
    const seq = ++requestSequence.current.value;
    setSelected(version);
    setPreview(null);
    setError("");
    try {
      const value = await getRecordVersion(id, version.id, shareToken);
      if (seq !== requestSequence.current.value) return;
      const doc = new Y.Doc();
      Y.applyUpdate(doc, decodeState(value.state));
      setPreview(doc);
    } catch (cause) {
      if (seq === requestSequence.current.value) setError((cause as Error).message);
    }
  }
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await provider.flush();
      await action();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(value) => {
        if (!value && !busy) close();
      }}
    >
      <DialogContent className="flex h-[80vh] max-w-5xl flex-col sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>版本历史</DialogTitle>
          <DialogDescription>
            自动保留编辑版本，也可手动保存命名版本。恢复前会备份当前内容。
          </DialogDescription>
        </DialogHeader>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        {status.document.owner && status.document.editable && (
          <div className="flex gap-2">
            <Input
              aria-label="版本名称"
              placeholder="为这个版本命名"
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              maxLength={100}
            />
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await checkpointRecord(id, label || "手动版本");
                  setVersions(await listRecordVersions(id, shareToken));
                  setLabel("");
                })
              }
            >
              <Save className="size-4" />
              保存版本
            </Button>
          </div>
        )}
        <div className="grid min-h-0 flex-1 grid-cols-[14rem_1fr] gap-4">
          <div className="space-y-2 overflow-auto">
            {versions.length ? (
              versions.map((version) => (
                <button
                  key={version.id}
                  className={`w-full rounded-lg border p-3 text-left text-sm ${selected?.id === version.id ? "border-primary bg-muted" : "hover:bg-muted/50"}`}
                  onClick={() => void select(version)}
                >
                  <span className="block font-medium">{version.label}</span>
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {new Date(version.created_at).toLocaleString()}
                    <br />
                    {version.author} · v{version.revision}
                  </span>
                </button>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">暂无历史版本</p>
            )}
          </div>
          <div className="flex min-h-0 flex-col rounded-lg border">
            <div className="flex items-center justify-between border-b px-4 py-2 text-sm">
              <span>{selected?.label ?? "选择版本预览"}</span>
              {selected && status.document.owner && status.document.editable && (
                <Popover>
                  <PopoverTrigger
                    render={
                      <Button variant="outline" size="sm" disabled={busy}>
                        恢复此版本
                      </Button>
                    }
                  />
                  <PopoverContent>
                    <p className="text-sm">恢复后将同步给所有协作者，当前内容会自动备份。</p>
                    <Button
                      className="mt-3"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          const current = await getRecord(id);
                          const value = await restoreRecord(id, selected.id, current.revision);
                          reset(value);
                          close();
                          toast.success("已恢复历史版本");
                        })
                      }
                    >
                      确认恢复
                    </Button>
                  </PopoverContent>
                </Popover>
              )}
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              <Suspense fallback={<p className="p-5">正在读取版本…</p>}>
                {preview && (
                  <Editor key={selected?.id} doc={preview} editable={false} username="历史版本" />
                )}
              </Suspense>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
