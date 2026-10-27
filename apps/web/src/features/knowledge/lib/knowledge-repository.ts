import { useAuthStore } from "@/stores/auth";
import { readMock, writeMock } from "@/lib/mock-storage";
import { KNOWLEDGE_BASES, type KbFile } from "../constants/knowledge-data";
import type { KnowledgeBase } from "../constants/knowledge-data";

export type StoredKnowledgeBase = KnowledgeBase & {
  accountId: string;
  createdAt: string;
  updatedAt: string;
  serverId?: number;
};
export type KnowledgeBaseInput = { name: string; description: string };
export type EditorDocumentInput = {
  preserveTitle?: boolean;
  id: string;
  title: string;
  content: string;
  blocks?: KbFile["blocks"];
  status: "draft" | "published";
};

function normalize(input: KnowledgeBaseInput): KnowledgeBaseInput {
  const name = input.name.trim();
  if (!name) throw new Error("请输入知识库名称。");
  return { name, description: input.description.trim() };
}

function localRecord(accountId: string, input: KnowledgeBaseInput): StoredKnowledgeBase {
  const user = useAuthStore.getState().user;
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    accountId,
    name: input.name.trim(),
    description: input.description.trim(),
    owner: user?.username ?? "我",
    files: [],
    documentCount: 0,
    createdAt: now,
    updatedAt: now,
  };
}

function load(accountId: string): StoredKnowledgeBase[] {
  const key = `knowledge:${accountId}`;
  const saved = readMock<StoredKnowledgeBase[]>(key);
  if (saved) return saved;
  const now = new Date().toISOString();
  const seeded = KNOWLEDGE_BASES.map((base, index) => ({
    ...base,
    id: String(index + 1),
    accountId,
    createdAt: now,
    updatedAt: now,
    documentCount: 0,
  }));
  writeMock(key, seeded);
  return seeded;
}
export async function listKnowledgeBases(accountId: string): Promise<StoredKnowledgeBase[]> {
  return load(accountId);
}
export async function createKnowledgeBase(accountId: string, input: KnowledgeBaseInput) {
  const bases = load(accountId);
  const nextId = Math.max(
    readMock<number>(`knowledge-next-id:${accountId}`) ?? 1,
    Math.max(0, ...bases.map((base) => Number(base.id)).filter(Number.isSafeInteger)) + 1,
  );
  const record = {
    ...localRecord(accountId, normalize(input)),
    id: String(nextId),
  };
  writeMock(`knowledge-next-id:${accountId}`, nextId + 1);
  writeMock(`knowledge:${accountId}`, [record, ...bases]);
  return record;
}

/** 缓存服务端新增记录。 */
export function cacheCreatedKnowledgeBase(accountId: string, record: StoredKnowledgeBase) {
  writeMock(`knowledge:${accountId}`, [
    record,
    ...load(accountId).filter((base) => base.id !== record.id),
  ]);
}
export async function updateKnowledgeBase(
  accountId: string,
  id: string,
  input: KnowledgeBaseInput,
) {
  const clean = normalize(input);
  const bases = load(accountId);
  const old = bases.find((base) => base.id === id);
  if (!old) throw new Error("知识库不存在。");
  const updated = { ...old, ...clean, updatedAt: new Date().toISOString() };
  writeMock(
    `knowledge:${accountId}`,
    bases.map((base) => (base.id === id ? updated : base)),
  );
  return updated;
}
export async function deleteKnowledgeBase(accountId: string, id: string) {
  writeMock(
    `knowledge:${accountId}`,
    load(accountId).filter((base) => base.id !== id),
  );
}
export async function addKnowledgeDocument(accountId: string, id: string, file: KbFile) {
  const bases = load(accountId);
  const base = bases.find((base) => base.id === id);
  if (!base) throw new Error("知识库不存在。");
  const updated = {
    ...base,
    files: [file, ...base.files.filter((row) => row.id !== file.id)],
    updatedAt: new Date().toISOString(),
  };
  writeMock(
    `knowledge:${accountId}`,
    bases.map((row) => (row.id === id ? updated : row)),
  );
  return updated;
}

export async function saveEditorDocument(
  accountId: string,
  baseId: string,
  input: EditorDocumentInput,
) {
  const title = input.title.trim().replace(/\.md$/i, "").trim();
  if (!title) throw new Error("请输入文档标题。");
  const base = load(accountId).find((row) => row.id === baseId);
  if (!base) throw new Error("知识库不存在。");
  const existing = base.files.find((row) => row.id === input.id);
  if (existing && existing.source !== "editor") throw new Error("此文档不支持在线编辑。");
  const file: KbFile = {
    id: input.id,
    name: `${title}.md`,
    type: "md",
    content: input.content,
    blocks: input.blocks,
    source: "editor",
    status: input.status,
    size: `${Math.max(1, Math.ceil(new TextEncoder().encode(input.content).byteLength / 1024))} KB`,
    uploader: existing?.uploader ?? useAuthStore.getState().user?.username ?? "我",
    updatedAt: new Date().toISOString().slice(0, 10),
  };
  return { base: await addKnowledgeDocument(accountId, baseId, file), file };
}

/** 同步服务端目录，保留尚未接入接口的本地文档。 */
export function cacheServerKnowledgeBases(
  accountId: string,
  records: StoredKnowledgeBase[],
  replace = true,
): StoredKnowledgeBase[] {
  const existing = load(accountId);
  const byId = new Map(existing.map((base) => [base.id, base]));
  const bases = records.map((record) => ({
    ...record,
    files: byId.get(record.id)?.files ?? [],
  }));
  writeMock(`knowledge:${accountId}`, [
    ...existing.filter(
      (base) =>
        base.serverId == null || (!replace && !records.some((record) => record.id === base.id)),
    ),
    ...bases,
  ]);
  return bases;
}

/** 仅供迁移读取旧版在线文档。 */
export function listLocalEditorDocuments(accountId: string, baseId: string): KbFile[] {
  return (
    load(accountId)
      .find((base) => base.id === baseId)
      ?.files.filter((file) => file.source === "editor") ?? []
  );
}

/** SQLite 保存成功后移除旧版本地副本。 */
export function removeLocalEditorDocuments(accountId: string, baseId: string, ids: string[]) {
  const keys = new Set(ids);
  writeMock(
    `knowledge:${accountId}`,
    load(accountId).map((base) =>
      base.id === baseId
        ? {
            ...base,
            files: base.files.filter((file) => file.source !== "editor" || !keys.has(file.id)),
          }
        : base,
    ),
  );
}

/** 删除尚未迁移到 SQLite 的本地文件记录。 */
export function removeLocalKnowledgeDocument(
  accountId: string,
  baseId: string,
  documentId: string,
) {
  writeMock(
    `knowledge:${accountId}`,
    load(accountId).map((base) =>
      base.id === baseId
        ? { ...base, files: base.files.filter((file) => file.id !== documentId) }
        : base,
    ),
  );
}
