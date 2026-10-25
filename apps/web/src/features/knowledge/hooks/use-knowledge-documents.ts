import { useEffect, useState } from "react";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
import { loadKnowledgeDocumentsRequest } from "@/apis/knowledge";
import type { KbFile } from "@/features/knowledge/constants/knowledge-data";
export function useKnowledgeDocuments(baseId: string) {
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const username = useAuthStore((state) => state.user?.username);
  const [state, setState] = useState<{
    key: string;
    files: KbFile[];
    loading: boolean;
    error: string | null;
  }>({ key: "", files: [], loading: true, error: null });
  const [version, setVersion] = useState(0);
  const key = `${accountId}:${baseId}`;
  useEffect(() => {
    let alive = true;
    if (!accountId) return;
    setState({ key, files: [], loading: true, error: null });
    loadKnowledgeDocumentsRequest(accountId, baseId)
      .then((rows) => {
        if (alive)
          setState({
            key,
            files: rows,
            loading: false,
            error: null,
          });
      })
      .catch((cause) => {
        if (alive)
          setState({
            key,
            files: [],
            loading: false,
            error: cause instanceof Error ? cause.message : "读取文档失败，请重试。",
          });
      });
    return () => {
      alive = false;
    };
  }, [accountId, baseId, key, username, version]);
  return {
    files: state.key === key ? state.files : [],
    loading: state.key !== key || state.loading,
    error: state.key === key ? state.error : null,
    reload: () => setVersion((v) => v + 1),
  };
}
