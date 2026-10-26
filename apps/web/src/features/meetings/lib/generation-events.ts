import type { Meeting } from "@/apis/meetings";
import { getAccessToken, useAuthStore } from "@/stores/auth";

type Listener = (meetings: Meeting[], snapshot: boolean) => void;
type Connection = {
  owner: number;
  token: string;
  listeners: Set<Listener>;
  latest: Map<string, Meeting>;
  hasSnapshot: boolean;
  stop: () => void;
};
let shared: Connection | null = null;

/** 同一登录会话的多个页面组件共用一条状态连接。 */
export function subscribeGenerationEvents(owner: number, listener: Listener): () => void {
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
    if (!alive || getAccessToken() !== token || useAuthStore.getState().user?.id !== owner) return;
    const url = new URL("/api/meetings/events", window.location.href);
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
        let updates: Meeting[];
        let snapshot = false;
        if (message.type === "meetings.snapshot" && Array.isArray(message.meetings)) {
          attempts = 0;
          snapshot = true;
          updates = message.meetings.filter((row: Meeting) => row.owner_id === owner);
          connection.latest = new Map(updates.map((row) => [row.id, row]));
          connection.hasSnapshot = true;
        } else if (message.type === "meeting.updated" && message.meeting?.owner_id === owner) {
          const row = message.meeting as Meeting;
          if ((connection.latest.get(row.id)?.revision ?? 0) > row.revision) return;
          connection.latest.set(row.id, row);
          updates = [row];
        } else if (message.type === "meeting.removed" && typeof message.meeting_id === "string") {
          connection.latest.delete(message.meeting_id);
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
