import { usePermission } from "@/features/access/hooks/use-permission";
import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";
import { syncNow, useMeetingCache } from "@/stores/meeting";
export function MeetingSync() {
  const canWrite = usePermission("meeting:write");
  const accountId = useAuthStore((state) => state.user?.id);
  useEffect(() => {
    useMeetingCache.setState({ records: {} });
  }, [accountId]);
  useEffect(() => {
    if (!accountId || !canWrite) return;
    const run = () => {
      void syncNow(accountId).catch(() => {});
    };
    run();
    const timer = setInterval(run, 5000);
    window.addEventListener("online", run);
    return () => {
      clearInterval(timer);
      window.removeEventListener("online", run);
    };
  }, [accountId, canWrite]);
  return null;
}
