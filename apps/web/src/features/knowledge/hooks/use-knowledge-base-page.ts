import { useCallback, useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
import { listKnowledgeBasesRequest, type KnowledgeBasePage } from "@/apis/knowledge";
import { cacheServerKnowledgeBases } from "@/features/knowledge/lib/knowledge-repository";

/** 同参数在途请求去重：effect、focus 等触发源并发时只发一次网络请求。 */
const inflight = new Map<string, Promise<KnowledgeBasePage>>();

export function useKnowledgeBasePage(
  q: string,
  page: number,
  pageSize: number,
  onPageChange: (page: number) => void,
) {
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const version = useRef(0);
  const [state, setState] = useState<{
    key: string;
    result: KnowledgeBasePage | null;
    loading: boolean;
    error: string | null;
  }>({ key: "", result: null, loading: true, error: null });
  const key = JSON.stringify([accountId, q, page, pageSize]);

  const reload = useCallback(async () => {
    const current = ++version.current;
    if (!accountId) return;
    setState((previous) => ({
      key,
      result: previous.key === key ? previous.result : null,
      loading: true,
      error: null,
    }));
    const requestKey = `${accountId}\u0000${q}\u0000${page}\u0000${pageSize}`;
    let result: KnowledgeBasePage;
    try {
      const inflightRequest = inflight.get(requestKey);
      if (inflightRequest) {
        result = await inflightRequest;
      } else {
        const promise = listKnowledgeBasesRequest(accountId, q, page, pageSize);
        inflight.set(requestKey, promise);
        try {
          result = await promise;
        } finally {
          if (inflight.get(requestKey) === promise) inflight.delete(requestKey);
        }
      }
    } catch (cause) {
      if (current !== version.current) return;
      setState((previous) => ({
        ...previous,
        key,
        loading: false,
        error: cause instanceof Error ? cause.message : "读取知识库失败，请重试。",
      }));
      return;
    }
    if (current !== version.current) return;
    const lastPage = Math.max(1, Math.ceil(result.total / pageSize));
    if (page > lastPage) {
      onPageChange(lastPage);
      return;
    }
    result.item = cacheServerKnowledgeBases(accountId, result.item, false);
    setState({ key, result, loading: false, error: null });
  }, [accountId, q, page, pageSize, key, onPageChange]);

  useEffect(() => {
    void reload();
    return () => {
      version.current += 1;
    };
  }, [reload]);

  return {
    result: state.key === key ? state.result : null,
    loading: state.key !== key || state.loading,
    error: state.key === key ? state.error : null,
    reload: () => void reload(),
  };
}
