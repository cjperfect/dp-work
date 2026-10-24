import { KNOWLEDGE_BASES, type KbFile } from "@/features/knowledge/constants/knowledge-data";

const STORAGE_PREFIX = "dp-work:kb-upload:";

function loadUploaded(kbId: string): KbFile[] {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + kbId);
    return raw ? (JSON.parse(raw) as KbFile[]) : [];
  } catch {
    return [];
  }
}

function saveUploaded(kbId: string, files: KbFile[]) {
  try {
    localStorage.setItem(STORAGE_PREFIX + kbId, JSON.stringify(files));
  } catch {
    /* 存储不可用时仅保留内存态 */
  }
}

/** 某知识库的全部文件 = 内置示例 + 本地上传 */
export function getKbFiles(kbId: string): KbFile[] {
  const kb = KNOWLEDGE_BASES.find((k) => k.id === kbId);
  const builtin = kb?.files ?? [];
  return [...loadUploaded(kbId), ...builtin];
}

/** 追加一个上传文件（md 存 content，pdf 存 dataUrl），写入 localStorage */
export function appendUploadedFile(kbId: string, file: KbFile) {
  const list = loadUploaded(kbId);
  saveUploaded(kbId, [file, ...list]);
}
