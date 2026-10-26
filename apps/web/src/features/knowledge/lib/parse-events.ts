import { getAccessToken, useAuthStore } from "@/stores/auth";

export type DocumentParseState = {
  id: string;
  base_id: number;
  owner_id: number;
  name: string;
  status: "queued" | "parsing" | "parsed" | "failed";
  task_id: string;
  error: string | null;
  parsed_at: string | null;
};
type Listener = (rows: DocumentParseState[], snapshot: boolean) => void;
type Connection = {
  owner: number;
  token: string;
  listeners: Set<Listener>;
  latest: Map<string, DocumentParseState>;
  hasSnapshot: boolean;
  stop: () => void;
};
let shared: Connection | null = null;

/** 全局通知和文档页面共用一条连接。 */
export function subscribeDocumentParseEvents(owner: number, listener: Listener): () => void {
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
      clearTimeout(timer);
      socket?.close();
      connection.listeners.clear();
      if (shared === connection) shared = null;
    },
  };
  const connect = () => {
    if (!alive || getAccessToken() !== token || useAuthStore.getState().user?.id !== owner) return;
    const url = new URL("/api/knowledge-bases/events", window.location.href);
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
        getAccessToken() !== token ||
        useAuthStore.getState().user?.id !== owner
      )
        return;
      try {
        const message = JSON.parse(event.data);
        let rows: DocumentParseState[];
        const snapshot = message.type === "documents.snapshot";
        if (snapshot && Array.isArray(message.documents)) {
          attempts = 0;
          rows = message.documents.filter((row: DocumentParseState) => row.owner_id === owner);
          connection.latest = new Map(rows.map((row) => [row.id, row]));
          connection.hasSnapshot = true;
        } else if (message.type === "document.updated" && message.document?.owner_id === owner) {
          const row = message.document as DocumentParseState;
          connection.latest.set(row.id, row);
          rows = [row];
        } else return;
        for (const notify of connection.listeners) notify(rows, snapshot);
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
