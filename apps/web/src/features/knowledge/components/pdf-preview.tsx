import { useEffect, useRef, useState } from "react";
import { Loader2, ZoomIn, ZoomOut } from "lucide-react";
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy } from "pdfjs-dist";
import { Button } from "@/components/ui/button";

if (typeof window !== "undefined") {
  // worker 文件放在 public/pdf/ 静态目录，避免 webpack 打包 mjs worker 的兼容问题
  GlobalWorkerOptions.workerSrc = "/pdf/pdf.worker.min.mjs";
}

/** PDF 在线预览：pdf.js 渲染，全部页连续排列，支持上下滚动与缩放 */
export function PdfPreview({ url }: { url: string }) {
  const canvasRefs = useRef<(HTMLCanvasElement | null)[]>([]);
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [scale, setScale] = useState(1.1);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    setState("loading");
    setDoc(null);
    const loadingTask = getDocument({ url });
    loadingTask.promise
      .then((d) => {
        if (cancelled) return;
        setDoc(d);
        setState("ready");
      })
      .catch((e) => {
        if (cancelled) return;
        console.error("[PdfPreview] load error:", e);
        setState("error");
      });
    return () => {
      cancelled = true;
      void loadingTask.destroy();
    };
  }, [url]);

  // 渲染全部页到各自的 canvas（纵向排列，容器滚动查看）
  useEffect(() => {
    if (!doc) return;
    let cancelled = false;
    const renderAll = async () => {
      for (let i = 1; i <= doc.numPages; i += 1) {
        if (cancelled) return;
        try {
          const pageData = await doc.getPage(i);
          const viewport = pageData.getViewport({ scale });
          const canvas = canvasRefs.current[i - 1];
          if (!canvas || cancelled) continue;
          const ctx = canvas.getContext("2d");
          if (!ctx) continue;
          canvas.width = viewport.width;
          canvas.height = viewport.height;
          await pageData.render({ canvas, canvasContext: ctx, viewport }).promise;
        } catch {
          /* 单页渲染失败静默，其余页仍可查看 */
        }
      }
    };
    void renderAll();
    return () => {
      cancelled = true;
    };
  }, [doc, scale]);

  if (state === "loading") {
    return (
      <div className="text-muted-foreground flex h-full min-h-64 flex-col items-center justify-center gap-2">
        <Loader2 className="size-6 animate-spin" />
        <p className="text-sm">正在解析 PDF…</p>
      </div>
    );
  }

  if (state === "error" || !doc) {
    return (
      <div className="text-muted-foreground flex h-full min-h-64 flex-col items-center justify-center gap-2">
        <p className="text-sm">PDF 解析失败，请下载后查看</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-border/60 bg-muted/30 flex items-center justify-between gap-3 border-b px-4 py-2 text-xs">
        <div className="text-muted-foreground flex items-center gap-3">
          <span>共 {doc.numPages} 页</span>
          <span className="flex items-center gap-0.5">
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="缩小"
              onClick={() => setScale((s) => Math.max(0.5, +(s - 0.15).toFixed(2)))}
            >
              <ZoomOut className="size-3.5" />
            </Button>
            <span className="w-10 text-center tabular-nums">{Math.round(scale * 100)}%</span>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="放大"
              onClick={() => setScale((s) => Math.min(3, +(s + 0.15).toFixed(2)))}
            >
              <ZoomIn className="size-3.5" />
            </Button>
          </span>
        </div>
      </div>
      <div className="bg-muted/20 flex-1 overflow-auto p-4">
        <div className="flex flex-col items-center gap-4">
          {Array.from({ length: doc.numPages }, (_, i) => (
            <canvas
              key={i}
              ref={(el) => {
                canvasRefs.current[i] = el;
              }}
              className="mx-auto shadow-sm transition-[width,height]"
              style={{ maxWidth: "100%", height: "auto" }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
