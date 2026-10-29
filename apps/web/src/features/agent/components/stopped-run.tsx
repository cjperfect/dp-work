import { useAuiState } from "@assistant-ui/react";
import { CircleStop } from "lucide-react";

/** 停止不会回滚文件；后续输入会在同一会话开启新的执行。 */
export function StoppedRunNotice() {
  const status = useAuiState((state) => state.message.metadata.custom.local_status);
  if (status !== "cancelled") return null;
  return (
    <p
      className="mt-2 flex items-start gap-1.5 text-xs leading-5 text-muted-foreground"
      role="status"
    >
      <CircleStop className="mt-1 size-3 shrink-0" />
      已停止。已完成的修改会保留，发送“接着运行”可继续处理。
    </p>
  );
}
