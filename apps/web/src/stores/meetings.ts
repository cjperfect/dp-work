import { trackGenerations } from "@/stores/meeting-generation";
import { create } from "zustand";
import { useCallback, useEffect, useState } from "react";
import { useAuthStore } from "@/stores/auth";
import { type Workspace } from "@/apis/meetings";
import {
  acceptServerWorkspace,
  isPending,
  localDraft,
  readDraft,
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
  trackGenerations([draft.meeting]);
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
    const current = useMeetingCache.getState().records[key(draft.accountId, draft.meeting.id)];
    if (current?.version === stored.version) stored.temporary = current.temporary;
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
  const current = useMeetingCache.getState().records[key(accountId, id)];
  if (current && (!current.localSaved || isPending(current))) return current;
  const stored = await readDraft(accountId, id);
  if (!stored) throw new Error("会议不存在或已删除。");
  if (active()) publish(stored);
  return stored;
}
const flights = new Map<number, Promise<void>>();
export function syncNow(accountId: number): Promise<void> {
  const running = flights.get(accountId);
  if (running) return running;
  const operation = (async () => {
    const records = Object.values(useMeetingCache.getState().records);
    for (const row of records) {
      if (row.accountId === accountId && (!row.localSaved || isPending(row))) await persist(row);
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
  const current = useMeetingCache.getState().records[key(accountId, id)];
  if (current && (!current.localSaved || isPending(current))) await persist(current);
  return readDraft(accountId, id);
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
    const load = loadWorkspace(accountId, id, () => alive);
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
      void loadWorkspace(accountId, id, () => alive).catch(() => {});
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
  const draft = localDraft(workspace);
  publish(draft);
  return Promise.resolve(draft);
}

export function cacheServerWorkspace(workspace: Workspace) {
  const previous =
    useMeetingCache.getState().records[key(workspace.meeting.owner_id, workspace.meeting.id)];
  if (previous && previous.meeting.revision > workspace.meeting.revision) return previous;
  const draft = acceptServerWorkspace(workspace, (previous?.version ?? 0) + 1);
  publish(draft);
  return draft;
}
