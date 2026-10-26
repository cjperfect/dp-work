import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { LazyBlockNoteEditor as Editor } from "@/components/editor/lazy-blocknote-editor";
import { saveParsedDocumentRequest } from "@/apis/knowledge";
import { localAccountId } from "@/features/auth/lib/auth";
import { useAuthStore } from "@/stores/auth";
import { DOCUMENTS_CHANGED } from "../hooks/use-document-parsing";
import type { KbFile } from "../constants/knowledge-data";

/** 解析结果单独编辑，1 秒防抖与 5 秒定时兜底保存。 */
export function ParsedDocumentEditor({
  baseId,
  file,
  onSaveStateChange,
}: {
  baseId: string;
  file: KbFile;
  onSaveStateChange: (blocked: boolean) => void;
}) {
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const [initial] = useState(file);
  const latest = useRef({ content: file.parsedContent ?? "", blocks: file.parsedBlocks });
  const timestamp = useRef(file.parsedAt!);
  const pending = useRef(false);
  const saving = useRef(false);
  const conflict = useRef(false);
  const [revision, setRevision] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [status, setStatus] = useState("已保存");
  const save = useCallback(
    async function persist(): Promise<void> {
      if (!accountId || !pending.current || saving.current || conflict.current) return;
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      const snapshot = latest.current;
      saving.current = true;
      let succeeded = false;
      setStatus("保存中…");
      try {
        const saved = await saveParsedDocumentRequest(accountId, baseId, file.id, {
          ...snapshot,
          expected_parsed_at: timestamp.current,
        });
        succeeded = true;
        timestamp.current = saved.parsedAt!;
        window.dispatchEvent(
          new CustomEvent(DOCUMENTS_CHANGED, {
            detail: { baseId, accountId, file: saved },
          }),
        );
        if (latest.current === snapshot) {
          pending.current = false;
          setDirty(false);
        }
        setStatus("已保存");
      } catch (cause) {
        const message = cause instanceof Error ? cause.message : "保存失败，请重试";
        if (message.includes("其他页面更新")) conflict.current = true;
        setStatus(message);
      } finally {
        saving.current = false;
        onSaveStateChange(pending.current || !latest.current.content.trim());
        if (succeeded && pending.current && latest.current !== snapshot) void persist();
      }
    },
    [accountId, baseId, file.id, onSaveStateChange],
  );
  useEffect(() => {
    const interval = setInterval(() => void save(), 5000);
    const flush = () => void save();
    const visibility = () => {
      if (document.visibilityState === "hidden") flush();
    };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      clearInterval(interval);
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", visibility);
      void save();
    };
  }, [save]);
  useEffect(() => {
    if (!revision) return;
    const timer = setTimeout(() => void save(), 1000);
    return () => clearTimeout(timer);
  }, [revision, save]);
  return (
    <>
      <div className="flex items-center justify-between gap-3 border-b px-5 py-3">
        <p role="status" className="text-xs text-muted-foreground">
          {dirty && status === "已保存" ? "未保存" : status}
        </p>
        <div className="flex gap-2">
          {dirty && !["已保存", "保存中…"].includes(status) && (
            <Button size="sm" variant="outline" onClick={() => void save()}>
              重试保存
            </Button>
          )}
        </div>
      </div>
      <Editor
        initialContent={initial.parsedBlocks}
        markdown={initial.parsedBlocks ? undefined : initial.parsedContent}
        className="px-4 py-4"
        onDocumentChange={({ markdown, blocks }) => {
          latest.current = { content: markdown, blocks };
          pending.current = true;
          onSaveStateChange(true);
          setDirty(true);
          setRevision((value) => value + 1);
        }}
      />
    </>
  );
}
