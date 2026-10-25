import { useCallback, useEffect } from "react";
import { create } from "zustand";
import { useAuthStore } from "@/stores/auth";
import { readMock, writeMock } from "@/lib/mock-storage";
import { CONNECTORS, type Connector } from "@/features/connectors/constants/connectors";

const EMPTY: Connector[] = [];
export const useConnectorStore = create<{ owner: number | null; connectors: Connector[] }>(() => ({
  owner: null,
  connectors: EMPTY,
}));

export function loadConnectors(owner: number | null) {
  if (owner === null) {
    useConnectorStore.setState({ owner: null, connectors: EMPTY });
    return;
  }
  if (useAuthStore.getState().user?.id !== owner) return;
  const connectors = readMock<Connector[]>(`connectors:${owner}`) ?? CONNECTORS;
  useConnectorStore.setState({ owner, connectors });
}

export function updateConnectors(owner: number, update: (current: Connector[]) => Connector[]) {
  if (useAuthStore.getState().user?.id !== owner) throw new Error("登录状态已改变，请重试。");
  const state = useConnectorStore.getState();
  const current =
    state.owner === owner
      ? state.connectors
      : (readMock<Connector[]>(`connectors:${owner}`) ?? CONNECTORS);
  const connectors = update(current);
  writeMock(`connectors:${owner}`, connectors);
  useConnectorStore.setState({ owner, connectors });
}

export function useConnectors() {
  const owner = useAuthStore((state) => state.user?.id ?? null);
  const state = useConnectorStore();
  useEffect(() => {
    loadConnectors(owner);
    const refresh = () => loadConnectors(owner);
    const onStorage = (event: StorageEvent) => {
      if (event.key === null || event.key === `dp-work:mock:v1:connectors:${owner}`) refresh();
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("storage", onStorage);
    };
  }, [owner]);
  const update = useCallback(
    (change: (current: Connector[]) => Connector[]) => {
      if (owner === null) return;
      updateConnectors(owner, change);
    },
    [owner],
  );
  return { connectors: state.owner === owner ? state.connectors : EMPTY, updateConnectors: update };
}
