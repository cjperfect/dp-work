import { localAccountId } from "@/features/auth/lib/auth";
import type { KbFile } from "@/features/knowledge/constants/knowledge-data";
import { useAuthStore } from "@/stores/auth";
import { useKnowledgeStore } from "@/stores/knowledge";

import { removeLocalKnowledgeDocument } from "@/features/knowledge/lib/knowledge-repository";

const STORAGE_PREFIX = "dp-work:kb-upload:v2:";

function storageKey(accountId: string, kbId: string) {
  if (!accountId) throw new Error("请先登录。");
  return STORAGE_PREFIX + JSON.stringify([accountId, kbId]);
}

function loadUploaded(kbId: string, accountId: string): KbFile[] {
  try {
    const raw = localStorage.getItem(storageKey(accountId, kbId));
    return raw ? (JSON.parse(raw) as KbFile[]) : [];
  } catch {
    return [];
  }
}

/** 当前账号知识库的文件：已保存的文件 + 本地上传 */
export function getKbFiles(kbId: string): KbFile[] {
  const accountId = localAccountId(useAuthStore.getState().user);
  const state = useKnowledgeStore.getState();
  if (!accountId || state.accountId !== accountId) return [];
  const kb = state.bases.find((base) => base.id === kbId);
  return kb ? [...loadUploaded(kbId, accountId), ...kb.files] : [];
}

/** 追加一个上传文件（md 存 content，pdf 存 dataUrl），写入 localStorage */
export function appendUploadedFile(kbId: string, file: KbFile, accountId: string) {
  const list = loadUploaded(kbId, accountId);
  localStorage.setItem(storageKey(accountId, kbId), JSON.stringify([file, ...list]));
}

/** 删除浏览器中的上传文件及对应展示记录。 */
export function removeUploadedFile(kbId: string, documentId: string, accountId: string) {
  if (localAccountId(useAuthStore.getState().user) !== accountId)
    throw new Error("登录状态已改变，请重试。");
  const list = loadUploaded(kbId, accountId);
  localStorage.setItem(
    storageKey(accountId, kbId),
    JSON.stringify(list.filter((file) => file.id !== documentId)),
  );
  removeLocalKnowledgeDocument(accountId, kbId, documentId);
  useKnowledgeStore.setState((state) => ({
    bases: state.bases.map((base) =>
      base.id === kbId
        ? { ...base, files: base.files.filter((file) => file.id !== documentId) }
        : base,
    ),
  }));
}
