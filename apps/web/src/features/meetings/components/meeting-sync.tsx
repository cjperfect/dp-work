import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";
import { syncNow, useMeetingCache } from "@/stores/meeting";
export function MeetingSync() {
  const accountId = useAuthStore((state) => state.user?.id);
  useEffect(() => {
    useMeetingCache.setState({ records: {} });
    if (!accountId) return;
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
  }, [accountId]);
  return null;
}
