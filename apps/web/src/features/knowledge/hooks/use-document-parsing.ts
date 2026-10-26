import { useRef, useState } from "react";
import { toast } from "sonner";
import { parseKnowledgeDocumentRequest, vectorizeKnowledgeDocumentRequest } from "@/apis/knowledge";
import { localAccountId } from "@/features/auth/lib/auth";
import { useAuthStore } from "@/stores/auth";
import type { KbFile } from "../constants/knowledge-data";

export const DOCUMENTS_CHANGED = "knowledge-documents-changed";

export function parseStatusLabel(file: KbFile) {
  if (file.vectorizedAt) return "已向量化";
  return file.parseStatus === "parsed" ? "已解析" : "未解析";
}

export function useDocumentParsing(baseId: string) {
  const lock = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  async function start(file: KbFile) {
    if (lock.current) return;
    if (!["pdf", "txt", "md", "docx"].includes(file.type)) {
      toast.info("当前支持 TXT、Markdown、PDF 和 DOCX 解析，旧版 DOC 请先另存为 DOCX。");
      return;
    }
    const accountId = localAccountId(useAuthStore.getState().user);
    if (!accountId) return;
    lock.current = true;
    setSubmitting(true);
    try {
      const result = await parseKnowledgeDocumentRequest(accountId, baseId, file.id);
      window.dispatchEvent(
        new CustomEvent(DOCUMENTS_CHANGED, { detail: { baseId, accountId, file: result } }),
      );
      toast.info(
        result.parseStatus === "parsed"
          ? "文档已解析，请在解析后文档中检查和调整。"
          : "已提交文档解析任务。",
      );
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "解析提交失败，请重试。");
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  }
  return { start, submitting };
}

/** 提交向量任务，完成状态由共享 WebSocket 推送。 */
export function useDocumentVectorization(baseId: string) {
  const lock = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  async function start(file: KbFile) {
    if (lock.current) return;
    const accountId = localAccountId(useAuthStore.getState().user);
    if (!accountId) return;
    lock.current = true;
    setSubmitting(true);
    try {
      const result = await vectorizeKnowledgeDocumentRequest(accountId, baseId, file);
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      window.dispatchEvent(
        new CustomEvent(DOCUMENTS_CHANGED, { detail: { baseId, accountId, file: result } }),
      );
      toast.info("已提交向量化任务，完成后会通知你。");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "向量化提交失败，请重试。");
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  }
  return { start, submitting };
}
