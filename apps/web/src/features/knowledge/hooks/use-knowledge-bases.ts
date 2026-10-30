import type { StoredKnowledgeBase } from "@/interfaces/knowledge";
import { localAccountId } from "@/features/auth/lib/auth";
import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";
import { loadKnowledgeBases, resetKnowledgeBases, useKnowledgeStore } from "@/stores/knowledge";

const EMPTY: StoredKnowledgeBase[] = [];

export function useKnowledgeBases(enabled = true) {
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const storeAccountId = useKnowledgeStore((s) => s.accountId);
  const bases = useKnowledgeStore((s) => s.bases);
  const status = useKnowledgeStore((s) => s.status);
  const storeError = useKnowledgeStore((s) => s.error);
  useEffect(() => {
    if (!accountId) {
      resetKnowledgeBases();
      return;
    }
    if (!enabled) return;
    void loadKnowledgeBases(accountId);
  }, [accountId, enabled]);
  const current = storeAccountId === accountId;
  return {
    bases: current ? bases : EMPTY,
    loading: !current || status === "idle" || status === "loading",
    error: current ? storeError : null,
    reload: () => {
      if (accountId) void loadKnowledgeBases(accountId, true);
    },
  };
}
