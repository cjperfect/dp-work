import { create } from "zustand";
import * as repository from "@/features/knowledge/lib/knowledge-repository";
import {
  createKnowledgeBaseRequest,
  listAllKnowledgeBasesRequest,
  updateKnowledgeBaseRequest,
  deleteKnowledgeBaseRequest,
} from "@/apis/knowledge";
import type {
  EditorDocumentInput,
  KnowledgeBaseInput,
  StoredKnowledgeBase,
} from "@/features/knowledge/lib/knowledge-repository";

type KnowledgeState = {
  accountId: string | null;
  bases: StoredKnowledgeBase[];
  status: "idle" | "loading" | "ready" | "error";
  error: string | null;
};

export const useKnowledgeStore = create<KnowledgeState>(() => ({
  accountId: null,
  bases: [],
  status: "idle",
  error: null,
}));
let loadVersion = 0;

export async function loadKnowledgeBases(accountId: string, force = false) {
  const state = useKnowledgeStore.getState();
  if (!force && state.accountId === accountId && ["ready", "loading"].includes(state.status))
    return;
  const version = ++loadVersion;
  useKnowledgeStore.setState({
    accountId,
    bases: state.accountId === accountId ? state.bases : [],
    status: "loading",
    error: null,
  });
  try {
    const records = await listAllKnowledgeBasesRequest(accountId);
    if (version !== loadVersion) return;
    const bases = repository.cacheServerKnowledgeBases(accountId, records);
    useKnowledgeStore.setState({ bases, status: "ready" });
  } catch (error) {
    if (version === loadVersion)
      useKnowledgeStore.setState({
        status: "error",
        error: error instanceof Error ? error.message : "读取知识库失败，请重试。",
      });
  }
}

function remember(accountId: string, record: StoredKnowledgeBase) {
  if (useKnowledgeStore.getState().accountId !== accountId) return;
  loadVersion += 1;
  useKnowledgeStore.setState((state) => ({
    status: "ready",
    error: null,
    bases: [record, ...state.bases.filter((base) => base.id !== record.id)].sort((a, b) =>
      b.updatedAt.localeCompare(a.updatedAt),
    ),
  }));
}

export async function createKnowledgeBase(accountId: string, input: KnowledgeBaseInput) {
  const record = await createKnowledgeBaseRequest(accountId, input);
  try {
    repository.cacheCreatedKnowledgeBase(accountId, record);
  } catch {
    remember(accountId, record);
    throw new Error("知识库已创建，但本地展示缓存保存失败。请勿重复提交。");
  }
  remember(accountId, record);
  return record;
}

export async function updateKnowledgeBase(
  accountId: string,
  id: string,
  input: KnowledgeBaseInput,
) {
  const record = await updateKnowledgeBaseRequest(accountId, id, input);
  const [cached] = repository.cacheServerKnowledgeBases(accountId, [record], false);
  remember(accountId, cached);
  return cached;
}

export async function deleteKnowledgeBase(accountId: string, id: string) {
  await deleteKnowledgeBaseRequest(accountId, id);
  await repository.deleteKnowledgeBase(accountId, id);
  if (useKnowledgeStore.getState().accountId === accountId) {
    loadVersion += 1;
    useKnowledgeStore.setState((state) => ({
      bases: state.bases.filter((base) => base.id !== id),
      status: "ready",
      error: null,
    }));
  }
}

export function resetKnowledgeBases() {
  loadVersion += 1;
  useKnowledgeStore.setState({ accountId: null, bases: [], status: "idle", error: null });
}

export async function saveKnowledgeDocument(
  accountId: string,
  baseId: string,
  input: EditorDocumentInput,
) {
  const result = await repository.saveEditorDocument(accountId, baseId, input);
  remember(accountId, result.base);
  return result.file;
}
