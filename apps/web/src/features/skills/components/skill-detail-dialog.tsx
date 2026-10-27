import { ExternalLink, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { InstalledSkill } from "@/apis/skills";

type Props = {
  skill: InstalledSkill | null;
  agentName: string;
  installed: boolean;
  busy: boolean;
  onClose(): void;
  onInstall(): void;
};

/** 复用列表元信息展示完整简介，打开弹窗不请求仓库。 */
export function SkillDetailDialog({
  skill,
  agentName,
  installed,
  busy,
  onClose,
  onInstall,
}: Props) {
  return (
    <Dialog
      open={skill !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="flex max-h-[85vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-xl">
        <DialogHeader className="border-b px-6 py-5 pr-12">
          <DialogTitle className="break-words text-lg">{skill?.name ?? "技能详情"}</DialogTitle>
          <DialogDescription className="mt-1 break-words text-xs">
            {skill?.source || "本机技能"} · {installed ? `已安装到${agentName}` : "未安装"}
          </DialogDescription>
        </DialogHeader>
        <div className="overflow-y-auto px-6 py-5">
          <h3 className="mb-2 text-sm font-medium">技能简介</h3>
          <p className="whitespace-pre-wrap break-words text-sm leading-7 text-muted-foreground">
            {skill?.description?.trim() || "暂未提供技能简介，可前往 skills.sh 查看。"}
          </p>
        </div>
        <DialogFooter className="m-0 flex-row items-center justify-between rounded-none px-6 py-4 sm:justify-between">
          {skill?.url ? (
            <a
              href={skill.url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-xs text-muted-foreground"
            >
              skills.sh
              <ExternalLink className="size-3" />
            </a>
          ) : (
            <span />
          )}
          {installed ? (
            <Button variant="outline" size="sm" onClick={onClose}>
              关闭
            </Button>
          ) : (
            <Button size="sm" disabled={!skill || busy} onClick={onInstall}>
              {busy && <Loader2 className="size-3.5 animate-spin" />}安装到{agentName}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
