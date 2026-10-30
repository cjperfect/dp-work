import type { KbFile } from "@/interfaces/knowledge";
import { useEffect, useState, useCallback, useRef } from "react";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
import { loadKnowledgeDocumentsRequest } from "@/apis/knowledge";

import { subscribeDocumentParseEvents } from "../lib/parse-events";
import { DOCUMENTS_CHANGED } from "../lib/document-events";

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
  const current = useRef(state);
  current.current = state;
  const reload = useCallback(() => setVersion((value) => value + 1), []);
  useEffect(() => {
    let alive = true;
    if (!accountId) return;
    setState((old) => (old.key === key ? old : { key, files: [], loading: true, error: null }));
    async function load() {
      try {
        const rows = await loadKnowledgeDocumentsRequest(accountId!, baseId);
        if (!alive) return;
        setState((old) => ({
          key,
          files: rows.map((row) => {
            const currentFile =
              old.key === key ? old.files.find((file) => file.id === row.id) : undefined;
            return currentFile && Date.parse(currentFile.updatedAt) > Date.parse(row.updatedAt)
              ? currentFile
              : row;
          }),
          loading: false,
          error: null,
        }));
      } catch (cause) {
        if (alive)
          setState((old) => ({
            ...old,
            key,
            loading: false,
            error: cause instanceof Error ? cause.message : "读取文档失败，请重试。",
          }));
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [accountId, baseId, key, username, version]);
  useEffect(() => {
    const changed = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      if (detail?.baseId === baseId && detail?.accountId === accountId) {
        if (detail.file)
          setState((old) => ({
            ...old,
            files: old.files.map((file) =>
              file.id === detail.file.id &&
              Date.parse(detail.file.updatedAt) >= Date.parse(file.updatedAt)
                ? detail.file
                : file,
            ),
          }));
        else reload();
      }
    };
    window.addEventListener(DOCUMENTS_CHANGED, changed);
    return () => window.removeEventListener(DOCUMENTS_CHANGED, changed);
  }, [accountId, baseId, reload]);
  useEffect(() => {
    const owner = useAuthStore.getState().user?.id;
    if (!owner) return;
    return subscribeDocumentParseEvents(owner, (rows) => {
      if (current.current.key !== key) return;
      const relevant = rows.filter(
        (row) =>
          `server-${row.base_id}` === baseId &&
          current.current.files.some(
            (file) =>
              file.id === row.id &&
              (file.parseStatus !== row.status ||
                (row.vector_status !== undefined && file.vectorStatus !== row.vector_status) ||
                (row.vector_task_id != null && file.vectorTaskId !== row.vector_task_id) ||
                (row.vector_done != null && file.vectorDone !== row.vector_done) ||
                (row.vectorized_at != null && row.vectorized_at !== file.vectorizedAt) ||
                (row.parsed_at &&
                  Date.parse(row.parsed_at) > Date.parse(file.parsedAt ?? "1970-01-01"))),
          ),
      );
      if (!relevant.length) return;
      if (
        relevant.some((row) => {
          const file = current.current.files.find((file) => file.id === row.id)!;
          return (
            ((row.status === "unparsed" || row.status === "parsed" || row.status === "failed") &&
              (file.parseStatus !== row.status ||
                (row.parsed_at &&
                  Date.parse(row.parsed_at) > Date.parse(file.parsedAt ?? "1970-01-01")))) ||
            ((row.vector_status === "indexed" || row.vector_status === "failed") &&
              (file.vectorStatus !== row.vector_status || file.vectorTaskId !== row.vector_task_id))
          );
        })
      )
        reload();
      else
        setState((old) => ({
          ...old,
          files: old.files.map((file) => {
            const update = relevant.find((row) => row.id === file.id);
            return update
              ? {
                  ...file,
                  parseStatus: update.status,
                  vectorStatus: update.vector_status ?? file.vectorStatus,
                  vectorTaskId: update.vector_task_id ?? undefined,
                  vectorDone: update.vector_done ?? file.vectorDone,
                  vectorTotal: update.vector_total ?? file.vectorTotal,
                  vectorError: update.vector_error ?? undefined,
                  vectorizedAt: update.vectorized_at ?? undefined,
                }
              : file;
          }),
        }));
    });
  }, [accountId, baseId, key, reload, state.loading]);
  return {
    files: state.key === key ? state.files : [],
    loading: state.key !== key || state.loading,
    error: state.key === key ? state.error : null,
    reload,
  };
}
