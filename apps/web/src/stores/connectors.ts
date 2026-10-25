import { useEffect } from "react";
import { create } from "zustand";
import { useAuthStore } from "@/stores/auth";
import { getFeishuStatus, type FeishuStatus } from "@/apis/connectors";
import { CONNECTORS, type Connector } from "@/features/connectors/constants/connectors";

const EMPTY: Connector[] = [];
export const useConnectorStore = create<{
  owner: number | null;
  connectors: Connector[];
  feishu: FeishuStatus | null;
  loading: boolean;
  error: string | null;
}>(() => ({ owner: null, connectors: EMPTY, feishu: null, loading: false, error: null }));
const inflight = new Map<number, Promise<void>>();
let version = 0;

export function applyFeishuStatus(owner: number, feishu: FeishuStatus) {
  if (useAuthStore.getState().user?.id !== owner) return;
  useConnectorStore.setState({
    owner,
    feishu,
    loading: false,
    error: null,
    connectors: CONNECTORS.map((connector) => ({
      ...connector,
      status: feishu.connected ? "connected" : "disconnected",
      account: feishu.account ?? undefined,
    })),
  });
}

export async function loadConnectors(owner: number | null): Promise<void> {
  if (owner === null) {
    version += 1;
    useConnectorStore.setState({
      owner: null,
      connectors: EMPTY,
      feishu: null,
      loading: false,
      error: null,
    });
    return;
  }
  if (useAuthStore.getState().user?.id !== owner) return;
  const active = inflight.get(owner);
  if (active) return active;
  const current = ++version;
  const same = useConnectorStore.getState().owner === owner;
  useConnectorStore.setState({
    owner,
    loading: true,
    error: null,
    ...(same ? {} : { connectors: CONNECTORS, feishu: null }),
  });
  const pending = (async () => {
    try {
      const status = await getFeishuStatus();
      if (version === current) applyFeishuStatus(owner, status);
    } catch (cause) {
      if (version === current && useAuthStore.getState().user?.id === owner)
        useConnectorStore.setState({
          loading: false,
          error: cause instanceof Error ? cause.message : "读取飞书状态失败，请重试。",
        });
    }
  })();
  inflight.set(owner, pending);
  try {
    await pending;
  } finally {
    if (inflight.get(owner) === pending) inflight.delete(owner);
  }
}

export function useConnectors() {
  const owner = useAuthStore((state) => state.user?.id ?? null);
  const state = useConnectorStore();
  const flow = state.owner === owner ? state.feishu?.flow : null;
  const waiting = flow?.state === "starting" || flow?.state === "waiting";
  useEffect(() => {
    void loadConnectors(owner);
    const refresh = () => {
      void loadConnectors(owner);
    };
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [owner]);
  useEffect(() => {
    if (!waiting || owner === null) return;
    const timer = setInterval(() => {
      void loadConnectors(owner);
    }, 2000);
    return () => clearInterval(timer);
  }, [waiting, owner]);
  const current = state.owner === owner;
  return {
    connectors: current ? state.connectors : EMPTY,
    feishu: current ? state.feishu : null,
    loading: current && state.loading,
    error: current ? state.error : null,
    reload: () => loadConnectors(owner),
  };
}
