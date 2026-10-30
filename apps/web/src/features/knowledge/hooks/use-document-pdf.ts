import type { KbFile } from "@/interfaces/knowledge";
import { useEffect, useState } from "react";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
import { downloadKnowledgeDocumentRequest } from "@/apis/knowledge";

/** 通过带认证的请求读取 PDF，退出页面后回收 Blob URL。 */
export function useDocumentPdf(baseId: string, file?: KbFile) {
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const [state, setState] = useState<{ key: string; url: string | null; error: string | null }>({
    key: "",
    url: null,
    error: null,
  });
  const serverPdf = file?.type === "pdf" && file.storage === "server";
  const id = file?.id;
  const key = `${accountId}:${baseId}:${id}`;
  useEffect(() => {
    if (!serverPdf || !accountId || !id) return;
    let alive = true;
    let url: string | null = null;
    void (async () => {
      try {
        const blob = await downloadKnowledgeDocumentRequest(accountId, baseId, id);
        if (!alive) return;
        url = URL.createObjectURL(blob);
        setState({ key, url, error: null });
      } catch (cause) {
        if (alive)
          setState({
            key,
            url: null,
            error: cause instanceof Error ? cause.message : "读取 PDF 失败，请重试。",
          });
      }
    })();
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [accountId, baseId, id, key, serverPdf]);
  return serverPdf
    ? { url: state.key === key ? state.url : null, error: state.key === key ? state.error : null }
    : { url: file?.pdfUrl ?? null, error: null };
}
