import { useEffect, useState } from "react";
import type { RecordProvider } from "../lib/record-provider";

export type RecordCollaborator = { id: number; username: string };

/** 按账号合并协作连接，只更新发生变化的在线成员列表。 */
export function recordCollaborators(
  states: Iterable<Record<string, unknown>>,
): RecordCollaborator[] {
  const people = new Map<number, RecordCollaborator>();
  for (const state of states) {
    const user = state.collaborator as Partial<RecordCollaborator> | undefined;
    if (
      user &&
      typeof user.id === "number" &&
      typeof user.username === "string" &&
      user.username.trim()
    )
      people.set(user.id, { id: user.id, username: user.username });
  }
  return [...people.values()].sort((a, b) => a.id - b.id);
}

export function useRecordCollaborators(provider: RecordProvider | null, connected: boolean) {
  const [people, setPeople] = useState<RecordCollaborator[]>([]);
  useEffect(() => {
    if (!provider || !connected) return;
    const update = () => {
      const next = recordCollaborators(provider.awareness.getStates().values());
      setPeople((previous) =>
        previous.length === next.length &&
        previous.every(
          (person, index) =>
            person.id === next[index].id && person.username === next[index].username,
        )
          ? previous
          : next,
      );
    };
    provider.awareness.on("change", update);
    update();
    return () => provider.awareness.off("change", update);
  }, [provider, connected]);
  return connected ? people : [];
}
