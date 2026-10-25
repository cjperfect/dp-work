import { create } from "zustand";
import { useCallback, useEffect, useState } from "react";
import { useAuthStore } from "@/stores/auth";
import { emptyWorkspace, type Workspace } from "@/apis/meetings";
import {
  isPending,
  listDrafts,
  localDraft,
  readDraft,
  replaceFromServer,
  saveDraft,
  type Draft,
} from "@/features/meetings/lib/workspace-storage";

type Cached = Draft & { localSaved: boolean };
export const useMeetingCache = create<{ records: Record<string, Cached> }>()(() => ({
  records: {},
}));
const key = (accountId: number, id: string) => `${accountId}:${id}`;
export function publish(draft: Draft, localSaved = true) {
  if (useAuthStore.getState().user?.id !== draft.accountId) return;
  const id = key(draft.accountId, draft.meeting.id);
  useMeetingCache.setState((state) => {
    const old = state.records[id];
    if (
      old &&
      (old.version > draft.version ||
        (old.version === draft.version && old.meeting.revision > draft.meeting.revision))
    )
      return state;
    return { records: { ...state.records, [id]: { ...draft, localSaved } } };
  });
}
export async function persist(draft: Draft) {
  publish(draft, false);
  try {
    const stored = await saveDraft(draft);
    publish(stored);
    return stored;
  } catch (error) {
    publish({ ...draft, error: error instanceof Error ? error.message : "本地保存失败" }, false);
    throw error;
  }
}
export async function loadWorkspace(
  accountId: number,
  id: string,
  active: () => boolean = () => true,
) {
  const stored = await readDraft(accountId, id);
  if (stored) {
    publish(stored);
    return stored;
  }
  // 业务 API 已下线：已有记录以本地为准，避免重新进入时将已结束的会议重置。
  const server = emptyWorkspace(id, accountId);
  if (!active()) return localDraft(server);
  const fresh = await replaceFromServer(server);
  publish(fresh);
  return fresh;
}
const flights = new Map<number, Promise<void>>();
export function syncNow(accountId: number): Promise<void> {
  const running = flights.get(accountId);
  if (running) return running;
  const operation = (async () => {
    // 业务 API 已下线：本地即权威，直接清除待同步标记，不发起请求。
    const drafts = await listDrafts(accountId);
    for (let row of drafts) {
      if (
        row.meeting.generation_status === "generating" &&
        row.meeting.generation_ready_at &&
        row.meeting.generation_ready_at <= Date.now()
      ) {
        row = await saveDraft({
          ...row,
          meeting: { ...row.meeting, generation_status: "ready", minutes_status: 1 },
          minutes: row.minutes ? { ...row.minutes, status: 1 } : null,
          version: row.version + 1,
        });
        publish(row);
      }
      if (!isPending(row)) continue;
      const draft = await readDraft(accountId, row.meeting.id);
      if (!draft) continue;
      const stored = await saveDraft({
        ...draft,
        dirtyControls: false,
        dirtyMinutes: false,
        dirtyEntries: [],
        flight: null,
        error: null,
      });
      publish(stored);
    }
  })();
  flights.set(accountId, operation);
  void operation
    .finally(() => {
      if (flights.get(accountId) === operation) flights.delete(accountId);
    })
    .catch(() => {});
  return operation;
}
export async function flushMeeting(accountId: number, id: string) {
  // 先等待已发出的批次，再发送期间新增的内容；全部来自持久化 outbox。
  for (let batch = 0; batch < 20; batch++) {
    await syncNow(accountId);
    const draft = await readDraft(accountId, id);
    if (!draft || !isPending(draft)) return draft;
  }
  throw new Error("仍有记录待同步，请稍后重试。");
}
export function useWorkspace(id: string | undefined) {
  const accountId = useAuthStore((state) => state.user?.id);
  const draft = useMeetingCache((state) =>
    id && accountId ? state.records[key(accountId, id)] : undefined,
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editable, setEditable] = useState(false);
  useEffect(() => {
    let alive = true;
    let release: (() => void) | undefined;
    const controller = new AbortController();
    setEditable(false);
    if (!id || !accountId) return;
    if (!navigator.locks) {
      setEditable(true);
      return;
    }
    void navigator.locks
      .request(
        `dp-work-meeting:${accountId}:${id}`,
        { signal: controller.signal },
        async (lock) => {
          if (!alive || !lock) return;
          setEditable(true);
          await new Promise<void>((resolve) => {
            release = resolve;
          });
        },
      )
      .catch(() => {
        if (alive) setEditable(false);
      });
    return () => {
      alive = false;
      controller.abort();
      release?.();
    };
  }, [id, accountId]);

  useEffect(() => {
    let alive = true;
    if (!id || !accountId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    const load = editable
      ? loadWorkspace(accountId, id, () => alive)
      : (async () => {
          const stored = await readDraft(accountId, id);
          // 业务 API 已下线：无本地草稿时用本地空工作区。
          const record = stored ?? localDraft(emptyWorkspace(id, accountId));
          if (alive) publish(record, !!stored);
        })();
    void load
      .catch((cause) => {
        if (alive) setError(cause instanceof Error ? cause.message : "无法加载会议");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [id, accountId, editable]);
  useEffect(() => {
    if (!id || !accountId) return;
    let alive = true;
    const refresh = () => {
      void readDraft(accountId, id)
        .then((stored) => {
          if (alive && stored) publish(stored);
        })
        .catch(() => {});
    };
    window.addEventListener("focus", refresh);
    return () => {
      alive = false;
      window.removeEventListener("focus", refresh);
    };
  }, [id, accountId]);
  const change = useCallback(
    (update: (current: Draft) => Draft) => {
      if (!id || !accountId || !editable) return;
      const current = useMeetingCache.getState().records[key(accountId, id)];
      if (!current) return;
      const next = update(current);
      next.version = current.version + 1;
      next.error = null;
      const operation = persist(next);
      void operation.catch(() => {});
      return operation;
    },
    [id, accountId, editable],
  );
  const preview = useCallback(
    (update: (current: Draft) => Draft) => {
      if (!id || !accountId || !editable) return;
      useMeetingCache.setState((state) => {
        const cacheKey = key(accountId, id);
        const current = state.records[cacheKey];
        if (!current) return state;
        return {
          records: {
            ...state.records,
            [cacheKey]: { ...update(current), localSaved: current.localSaved },
          },
        };
      });
    },
    [id, accountId, editable],
  );
  const retry = useCallback(async () => {
    if (!id || !accountId) return;
    const current = useMeetingCache.getState().records[key(accountId, id)];
    if (current && !current.localSaved) await persist(current);
    await flushMeeting(accountId, id);
  }, [id, accountId]);
  return { draft, loading, error, change, preview, retry, accountId, editable };
}
export function cacheCreated(workspace: Workspace) {
  return persist(localDraft(workspace));
}
