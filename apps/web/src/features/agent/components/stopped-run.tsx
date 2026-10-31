import { useAuiState } from "@assistant-ui/react";
import { CircleStop } from "lucide-react";

/** 中断后直接发送续接指令，无需额外的恢复按钮。 */
export function StoppedRunNotice() {
  const status = useAuiState((state) => state.message.metadata.custom.local_status);
  const recovery = useAuiState((state) => state.message.metadata.custom.recovery);
  if (status !== "cancelled" && !(status === "failed" && recovery)) return null;
  return (
    <p
      className="mt-2 flex items-start gap-1.5 text-xs leading-5 text-muted-foreground"
      role="status"
    >
      <CircleStop className="mt-1 size-3 shrink-0" />
      {recovery
        ? "任务已中断，已保留执行进度。发送“接着执行”即可继续。"
        : "已停止，已完成的修改会保留。可发送新消息继续处理。"}
    </p>
  );
}
