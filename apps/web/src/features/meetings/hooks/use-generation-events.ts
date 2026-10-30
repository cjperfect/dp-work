import type { Meeting } from "@/interfaces/meeting";
import { useEffect, useRef } from "react";
import { useAuthStore } from "@/stores/auth";

import { subscribeGenerationEvents } from "../lib/generation-events";

/** 仅生成期间订阅状态变化，不定时请求会议列表。 */
export function useGenerationEvents(
  enabled: boolean,
  onUpdate: (meetings: Meeting[], snapshot: boolean) => void,
) {
  const owner = useAuthStore((state) => state.user?.id);
  const callback = useRef(onUpdate);
  callback.current = onUpdate;
  useEffect(() => {
    if (!enabled || !owner) return;
    return subscribeGenerationEvents(owner, (rows, snapshot) => callback.current(rows, snapshot));
  }, [enabled, owner]);
}
