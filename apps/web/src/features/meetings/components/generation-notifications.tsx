import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth";
import {
  finishGenerations,
  trackGenerations,
  useMeetingGenerationStore,
} from "@/stores/meeting-generation";
import { useGenerationEvents } from "../hooks/use-generation-events";

/** 登录期间在全局显示生成结果，路由切换不中断订阅。 */
export function GenerationNotifications() {
  const owner = useAuthStore((state) => state.user?.id);
  return owner ? <OwnerNotifications key={owner} owner={owner} /> : null;
}

function OwnerNotifications({ owner }: { owner: number }) {
  const [initialized, setInitialized] = useState(false);
  const pending = useMeetingGenerationStore((state) =>
    Object.values(state.pending).some((task) => task.ownerId === owner),
  );
  useEffect(
    () => () => {
      toast.dismiss();
    },
    [],
  );
  useGenerationEvents(!initialized || pending, (rows, snapshot) => {
    if (snapshot) {
      trackGenerations(rows);
      setInitialized(true);
    }
    for (const meeting of finishGenerations(rows, snapshot)) {
      const id = `meeting-generation:${owner}:${meeting.generation_task_id}`;
      if (meeting.generation_status === "ready") {
        toast.success("会议纪要已生成", {
          id,
          description: meeting.title,
          duration: 6000,
        });
      } else {
        toast.error("会议纪要生成失败", {
          id,
          description: `${meeting.title}：${meeting.generation_error || "请稍后重试。"}`,
          duration: 8000,
        });
      }
    }
  });
  return null;
}
