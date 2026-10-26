import { localAccountId } from "@/features/auth/lib/auth";
import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";
import { loadKnowledgeBases, resetKnowledgeBases, useKnowledgeStore } from "@/stores/knowledge";
import type { StoredKnowledgeBase } from "@/features/knowledge/lib/knowledge-repository";

const EMPTY: StoredKnowledgeBase[] = [];

export function useKnowledgeBases(enabled = true) {
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const state = useKnowledgeStore();
  useEffect(() => {
    if (!accountId) {
      resetKnowledgeBases();
      return;
    }
    if (!enabled) return;
    void loadKnowledgeBases(accountId);
    const refresh = () => {
      void loadKnowledgeBases(accountId, true);
    };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [accountId, enabled]);
  const current = state.accountId === accountId;
  return {
    bases: current ? state.bases : EMPTY,
    loading: !current || state.status === "idle" || state.status === "loading",
    error: current ? state.error : null,
    reload: () => {
      if (accountId) void loadKnowledgeBases(accountId, true);
    },
  };
}
