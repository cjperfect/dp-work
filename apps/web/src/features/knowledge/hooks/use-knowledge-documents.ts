import { useEffect, useState } from "react";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
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
    // 业务 API 已下线：静态空实现，不再发起请求。
    Promise.resolve([] as KbFile[]).then((rows) => {
      if (alive)
        setState({
          key,
          files: rows,
          loading: false,
          error: null,
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
