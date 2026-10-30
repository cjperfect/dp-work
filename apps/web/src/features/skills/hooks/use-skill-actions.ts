import type { InstalledSkill } from "@/interfaces/skills";
import type { AgentId } from "@/interfaces/app";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { installSkill, uninstallSkill, uploadSkill } from "@/apis/skills";

import { getAccessToken } from "@/stores/auth";
import { loadSkills } from "@/stores/skills";

type Operation = {
  id: string;
  execute: () => Promise<unknown>;
  success: string;
  failure: string;
  refreshFailure: string;
  onSuccess?: () => void;
};

/** 统一技能变更的互斥、账号校验、列表刷新和反馈。 */
export function useSkillActions(
  code: AgentId,
  agentName: string | undefined,
  onUploaded: () => void,
  onUninstalled: () => void,
) {
  const pending = useRef(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  async function run(operation: Operation) {
    if (pending.current) return;
    const token = getAccessToken();
    pending.current = true;
    setBusy(operation.id);
    setOperationError(null);
    try {
      await operation.execute();
      if (token !== getAccessToken()) return;
      const refreshed = await loadSkills(code, true);
      if (token !== getAccessToken()) return;
      operation.onSuccess?.();
      if (refreshed) toast.success(operation.success);
      else toast.warning(operation.refreshFailure);
    } catch (cause) {
      if (token === getAccessToken())
        setOperationError(cause instanceof Error ? cause.message : operation.failure);
    } finally {
      pending.current = false;
      setBusy(null);
    }
  }
  return {
    busy,
    operationError,
    clearError: () => setOperationError(null),
    upload: (file: File) =>
      agentName
        ? run({
            id: "upload",
            execute: () => uploadSkill(code, file),
            success: `技能已上传到${agentName}`,
            failure: "上传失败。",
            refreshFailure: "上传成功，列表刷新失败，请手动刷新。",
            onSuccess: onUploaded,
          })
        : Promise.resolve(),
    install: (source: string) =>
      agentName
        ? run({
            id: source,
            execute: () => installSkill(code, source),
            success: `已安装到${agentName}，下次对话自动加载`,
            failure: "安装失败，请重试。",
            refreshFailure: "技能已安装，但列表刷新失败，请点击刷新重试。",
          })
        : Promise.resolve(),
    uninstall: (skill: InstalledSkill) =>
      run({
        id: skill.id,
        execute: () => uninstallSkill(code, skill.id),
        success: "技能已卸载",
        failure: "卸载失败，请重试。",
        refreshFailure: "技能已卸载，但列表刷新失败，请点击刷新重试。",
        onSuccess: onUninstalled,
      }),
  };
}
