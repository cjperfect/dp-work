import type { UsageCategory } from "@/interfaces/usage";
import { http } from "@/lib/http";

/** 获取当前账号的本机累计用量。 */
export const getUsage = () => http.get<{ items: UsageCategory[] }>("/api/usage");
