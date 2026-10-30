import type { AgentConfig } from "@/interfaces/agent";
import type { AgentId } from "@/interfaces/app";
import { Link, useLocation } from "@tanstack/react-router";
import type * as React from "react";
import { BookOpen, Bot, Boxes, Package, Plug, Video, UsersRound, Palette } from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { ProjectSidebar } from "@/features/agent/components/project-sidebar";
import {
  ThreadListNew,
  ThreadListRoot,
  ThreadList,
} from "@/components/assistant-ui/elements/thread-list.aui";
import { useAgentStore } from "@/stores/agent";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";
import { useConnectors } from "@/stores/connectors";

import { useAuthStore } from "@/stores/auth";
import { UserMenu } from "@/features/auth/components/user-menu";

const EMPTY_AGENTS: AgentConfig[] = [];
const EMPTY_PARTNERS: AgentId[] = [];

const SPACE_NAV: {
  key: string;
  label: string;
  path: "/meetings" | "/skills" | "/knowledge" | "/connectors" | "/partners";
  icon: typeof Video;
}[] = [
  { key: "meetings", label: "开始会议", path: "/meetings", icon: Video },
  {
    key: "skills",
    label: "技能配置",
    path: "/skills",
    icon: Package,
  },
  { key: "knowledge", label: "知识库", path: "/knowledge", icon: BookOpen },
  {
    key: "connectors",
    label: "连接器",
    path: "/connectors",
    icon: Plug,
  },
  { key: "partners", label: "伙伴", path: "/partners", icon: UsersRound },
];

// 通用 Agent 默认显示，部门伙伴由用户从伙伴页添加。
const AGENT_NAV: {
  id: AgentId;
  label: string;
  path: "/" | "/product" | "/ui";
  icon: typeof Bot;
}[] = [
  { id: "general", label: "通用 Agent", path: "/", icon: Bot },
  { id: "product", label: "产品 Agent", path: "/product", icon: Boxes },
  { id: "ui", label: "UI Agent", path: "/ui", icon: Palette },
];

export function ThreadListSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { pathname } = useLocation();
  const user = useAuthStore((state) => state.user);
  const agents = useAgentStore((state) => (state.owner === user?.id ? state.agents : EMPTY_AGENTS));
  const partnerCodes = useAgentStore((state) =>
    state.owner === user?.id ? state.partnerCodes : EMPTY_PARTNERS,
  );
  const agentCode = useAgentCode();
  const installedCount = agents.find((agent) => agent.code === agentCode)?.skill_ids.length ?? 0;
  const { connectors } = useConnectors();
  const connectedCount = connectors.filter((connector) => connector.status === "connected").length;

  return (
    <Sidebar {...props}>
      <SidebarHeader className="aui-sidebar-header mb-2 border-b">
        <div className="aui-sidebar-header-content flex items-center justify-between">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" render={<Link to="/" />}>
                <img
                  src="/app-icon.png"
                  alt=""
                  className="aui-sidebar-header-icon size-8 shrink-0"
                />
                <div className="aui-sidebar-header-heading me-6 flex flex-col gap-0.5 leading-none">
                  <span className="aui-sidebar-header-title font-semibold">企业Agent平台</span>
                </div>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </div>
      </SidebarHeader>
      <SidebarContent className="aui-sidebar-content px-2">
        <SidebarGroup>
          <SidebarGroupLabel>{"我的空间"}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {SPACE_NAV.map((item) => {
                const Icon = item.icon;
                const count =
                  item.key === "skills"
                    ? installedCount
                    : item.key === "connectors"
                      ? connectedCount
                      : undefined;
                return (
                  <SidebarMenuItem key={item.key}>
                    <SidebarMenuButton
                      isActive={pathname === item.path || pathname.startsWith(`${item.path}/`)}
                      render={<Link to={item.path} />}
                    >
                      <Icon />
                      <span>{item.label}</span>
                      {typeof count === "number" && count > 0 && (
                        <span className="bg-sidebar-primary text-sidebar-primary-foreground ml-auto flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] font-medium">
                          {count}
                        </span>
                      )}
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>{"我的 Agent"}</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {AGENT_NAV.filter(
                (item) => item.id === "general" || partnerCodes.includes(item.id),
              ).map((item) => {
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.id}>
                    <SidebarMenuButton
                      isActive={pathname === item.path}
                      render={<Link to={item.path} />}
                    >
                      <Icon />
                      <span>
                        {agents.find((agent) => agent.code === item.id)?.name ?? item.label}
                      </span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup className="py-1">
          <ThreadListRoot>
            <ThreadListNew className="w-full" />
          </ThreadListRoot>
        </SidebarGroup>
        <ProjectSidebar />
        <SidebarGroup>
          <SidebarGroupLabel>{"最近"}</SidebarGroupLabel>
          <SidebarGroupContent>
            <ThreadList showNew={false} />
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      {props.collapsible !== "none" && <SidebarRail />}
      <SidebarFooter className="aui-sidebar-footer border-t">
        <UserMenu />
      </SidebarFooter>
    </Sidebar>
  );
}
