import type { RecordProvider } from "../lib/record-provider";
import { Avatar, AvatarFallback, AvatarGroup, AvatarGroupCount } from "@/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuthStore } from "@/stores/auth";
import { useRecordCollaborators } from "../hooks/use-record-collaborators";
import { collaboratorColor, collaboratorInitials } from "../lib/collaboration-cursor";

/** 展示此文档当前在线的协作者，包括自己。 */
export function RecordCollaborators({
  provider,
  connected,
}: {
  provider: RecordProvider | null;
  connected: boolean;
}) {
  const people = useRecordCollaborators(provider, connected);
  const currentId = useAuthStore((state) => state.user?.id);
  if (!people.length) return null;
  const visible = people.slice(0, 5);
  const remaining = people.slice(5);
  return (
    <div className="flex items-center gap-2" aria-label={`当前 ${people.length} 人正在协作`}>
      <AvatarGroup>
        {visible.map((person) => {
          const name = `${person.username}${person.id === currentId ? "（我）" : ""}`;
          return (
            <Tooltip key={person.id}>
              <TooltipTrigger render={<Avatar size="sm" tabIndex={0} aria-label={name} />}>
                <AvatarFallback
                  className="text-white"
                  style={{ backgroundColor: collaboratorColor(person.id) }}
                >
                  {collaboratorInitials(person.username)}
                </AvatarFallback>
              </TooltipTrigger>
              <TooltipContent>{name}</TooltipContent>
            </Tooltip>
          );
        })}
        {remaining.length > 0 && (
          <Tooltip>
            <TooltipTrigger
              render={
                <AvatarGroupCount
                  tabIndex={0}
                  aria-label={`另外 ${remaining.length} 人：${remaining.map((person) => person.username).join("、")}`}
                />
              }
            >
              +{remaining.length}
            </TooltipTrigger>
            <TooltipContent>{remaining.map((person) => person.username).join("、")}</TooltipContent>
          </Tooltip>
        )}
      </AvatarGroup>
      <span className="whitespace-nowrap text-xs text-muted-foreground">
        {people.length} 人正在协作
      </span>
    </div>
  );
}
