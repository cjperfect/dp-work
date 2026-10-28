import { useEffect, useRef, useState } from "react";
import { FileText, Loader2, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadKnowledgeDocumentRequest } from "@/apis/knowledge";

/** DOCX 源文件只读预览，保留分页和排版；渲染库按需加载。 */
export function DocxPreview({
  accountId,
  baseId,
  fileId,
}: {
  accountId: string;
  baseId: string;
  fileId: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; error?: string }>({ key: "" });
  const key = `${accountId}:${baseId}:${fileId}:${attempt}`;
  const ready = state.key === key;

  useEffect(() => {
    const target = container.current;
    if (!target) return;
    const controller = new AbortController();
    const stage = document.createElement("div");
    target.replaceChildren(stage);
    async function render() {
      try {
        const [{ renderAsync }, blob] = await Promise.all([
          import("docx-preview"),
          downloadKnowledgeDocumentRequest(accountId, baseId, fileId, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        await renderAsync(blob, stage, stage, {
          className: "knowledge-docx",
          breakPages: true,
          ignoreLastRenderedPageBreak: false,
          useBase64URL: true,
          renderAltChunks: false,
        });
        if (!controller.signal.aborted) setState({ key });
      } catch {
        if (!controller.signal.aborted) {
          stage.replaceChildren();
          setState({ key, error: "Word 预览失败，请重试或下载源文件查看。" });
        }
      }
    }
    void render();
    return () => {
      controller.abort();
      stage.remove();
    };
  }, [accountId, baseId, fileId, key]);

  return (
    <div className="min-h-64 bg-muted/30" aria-label="Word 文档预览" aria-busy={!ready}>
      {!ready && (
        <div
          role="status"
          className="flex items-center justify-center gap-2 p-10 text-sm text-muted-foreground"
        >
          <Loader2 className="size-4 animate-spin" />
          正在加载 Word 文档…
        </div>
      )}
      {ready && state.error && (
        <div
          role="alert"
          className="flex flex-col items-center gap-3 p-10 text-center text-sm text-muted-foreground"
        >
          <FileText className="size-8" />
          <p>{state.error}</p>
          <Button variant="outline" size="sm" onClick={() => setAttempt((value) => value + 1)}>
            <RotateCw className="size-4" />
            重新加载
          </Button>
        </div>
      )}
      <div
        ref={container}
        className={`${ready && !state.error ? "" : "hidden"} overflow-auto text-black [color-scheme:light] [&_.knowledge-docx-wrapper]:min-w-fit [&_.knowledge-docx-wrapper]:bg-transparent [&_.knowledge-docx-wrapper]:p-6`}
      />
    </div>
  );
}
