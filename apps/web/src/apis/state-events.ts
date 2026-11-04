import { getAccessToken, useAuthStore } from "@/stores/auth";

type StateRow = { id: string; owner_id: number };
type Listener<T> = (rows: T[], snapshot: boolean) => void;
type StateEvents<T> = {
  path: string;
  snapshotType: string;
  snapshotKey: string;
  updateType: string;
  updateKey: string;
  removedType?: string;
  removedKey?: string;
  isStale?: (previous: T | undefined, next: T) => boolean;
};

/** 每种业务共享一条连接，统一账号隔离、快照回放和重连。 */
export function createStateSubscription<T extends StateRow>(options: StateEvents<T>) {
  type Connection = {
    owner: number;
    token: string;
    listeners: Set<Listener<T>>;
    latest: Map<string, T>;
    hasSnapshot: boolean;
    stop: () => void;
  };
  let shared: Connection | null = null;

  /** 同一登录会话的多个页面组件共用一条状态连接。 */
  function subscribe(owner: number, listener: Listener<T>): () => void {
    const token = getAccessToken();
    if (!token || useAuthStore.getState().user?.id !== owner) return () => {};
    if (shared && (shared.owner !== owner || shared.token !== token)) shared.stop();
    if (!shared) shared = createConnection(owner, token);
    const connection = shared;
    connection.listeners.add(listener);
    if (connection.hasSnapshot)
      queueMicrotask(() => {
        if (connection.listeners.has(listener)) listener([...connection.latest.values()], true);
      });
    return () => {
      connection.listeners.delete(listener);
      // StrictMode 的 Effect 重放可在同一轮重新订阅，避免重复建连。
      queueMicrotask(() => {
        if (!connection.listeners.size) connection.stop();
      });
    };
  }

  function createConnection(owner: number, token: string): Connection {
    let alive = true;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const connection: Connection = {
      owner,
      token,
      listeners: new Set(),
      latest: new Map(),
      hasSnapshot: false,
      stop: () => {
        if (!alive) return;
        alive = false;
        if (timer) clearTimeout(timer);
        socket?.close();
        connection.listeners.clear();
        if (shared === connection) shared = null;
      },
    };
    const connect = () => {
      if (!alive || getAccessToken() !== token || useAuthStore.getState().user?.id !== owner)
        return;
      const url = new URL(options.path, window.location.href);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      const current = new WebSocket(url.href);
      socket = current;
      current.onopen = () => {
        if (alive && socket === current) current.send(JSON.stringify({ token }));
      };
      current.onmessage = (event) => {
        if (
          !alive ||
          socket !== current ||
          useAuthStore.getState().user?.id !== owner ||
          getAccessToken() !== token
        )
          return;
        try {
          const message = JSON.parse(event.data);
          let updates: T[];
          let snapshot = false;
          if (
            message.type === options.snapshotType &&
            Array.isArray(message[options.snapshotKey])
          ) {
            attempts = 0;
            snapshot = true;
            updates = (message[options.snapshotKey] as T[]).filter((row) => row.owner_id === owner);
            connection.latest = new Map(updates.map((row) => [row.id, row]));
            connection.hasSnapshot = true;
          } else if (
            message.type === options.updateType &&
            message[options.updateKey]?.owner_id === owner
          ) {
            const row = message[options.updateKey] as T;
            if (options.isStale?.(connection.latest.get(row.id), row)) return;
            connection.latest.set(row.id, row);
            updates = [row];
          } else if (
            options.removedType &&
            message.type === options.removedType &&
            options.removedKey &&
            typeof message[options.removedKey] === "string"
          ) {
            connection.latest.delete(message[options.removedKey]);
            updates = [...connection.latest.values()];
            snapshot = true;
          } else return;
          for (const notify of connection.listeners) notify(updates, snapshot);
        } catch {
          current.close();
        }
      };
      current.onclose = (event) => {
        if (alive && event.code !== 4401)
          timer = setTimeout(connect, Math.min(30000, 1000 * 2 ** attempts++));
      };
    };
    connect();
    return connection;
  }

  return subscribe;
}
