import { useCallback, useEffect, useRef, useState } from "react";
import { LazyBlockNoteEditor as Editor } from "@/components/editor/lazy-blocknote-editor";
import { saveKnowledgeDocument } from "@/stores/knowledge";
import { Button } from "@/components/ui/button";
import type { KbFile } from "../constants/knowledge-data";

/**
 * 知识库查看页「源文档」tab 的可编辑编辑器。
 * 新建文档（editor 来源）点开后在此继续编写，编辑内容自动保存，
 * 右下角展示「已保存 / 保存中… / 保存失败」状态，失败可重试。
 */
export function EditableSourceEditor({
  accountId,
  baseId,
  file,
}: {
  accountId: string;
  baseId: string;
  file: KbFile;
}) {
  const documentRef = useRef<{ blocks: KbFile["blocks"]; content: string }>({
    blocks: file.blocks ?? [],
    content: file.content ?? "",
  });
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const savingRef = useRef(false);
  const pendingRef = useRef(false);
  const [dirty, setDirty] = useState(false);
  const [failed, setFailed] = useState(false);

  const save = useCallback(async () => {
    if (savingRef.current) {
      pendingRef.current = true;
      return;
    }
    savingRef.current = true;
    try {
      await saveKnowledgeDocument(accountId, baseId, {
        id: file.id,
        title: file.name.replace(/\.md$/i, "").trim() || "未命名文档",
        content: documentRef.current.content,
        blocks: documentRef.current.blocks,
        status: "published",
      });
      setFailed(false);
      setDirty(false);
    } catch {
      setFailed(true);
    } finally {
      savingRef.current = false;
      if (pendingRef.current) {
        pendingRef.current = false;
        void save();
      }
    }
  }, [accountId, baseId, file.id, file.name]);

  useEffect(() => {
    const flush = () => {
      if (saveTimer.current) {
        clearTimeout(saveTimer.current);
        saveTimer.current = null;
        void save();
      }
    };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      document.removeEventListener("visibilitychange", flush);
      flush();
    };
  }, [save]);

  return (
    <div className="relative flex h-full min-h-0 flex-col">
      <Editor
        initialContent={file.blocks}
        markdown={file.blocks ? undefined : file.content}
        editable
        onDocumentChange={({ blocks: nextBlocks, markdown }) => {
          documentRef.current = { blocks: nextBlocks, content: markdown };
          setDirty(true);
          setFailed(false);
          if (saveTimer.current) clearTimeout(saveTimer.current);
          saveTimer.current = setTimeout(() => void save(), 1200);
        }}
        className="min-h-0 flex-1 px-4 py-4"
      />
      <div role="status" className="absolute bottom-2 right-3 flex items-center gap-2 text-[11px]">
        <span className={failed ? "text-destructive" : "text-muted-foreground"}>
          {failed ? "保存失败" : dirty ? "保存中…" : "已保存"}
        </span>
        {failed && (
          <Button size="xs" variant="outline" onClick={() => void save()}>
            重试保存
          </Button>
        )}
      </div>
    </div>
  );
}
