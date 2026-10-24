"use client";

import { Link, useLocation } from "@tanstack/react-router";
import type * as React from "react";
import { BookOpen, Bot, Boxes, Package, Plug, Sparkles, Video } from "lucide-react";
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
import { ThreadList } from "@/components/assistant-ui/elements/thread-list.aui";
import { SKILLS } from "@/features/skills/constants/skills";
import { CONNECTORS } from "@/features/connectors/constants/connectors";
import type { AgentId } from "@/interfaces/app";

const SPACE_NAV: {
  key: string;
  label: string;
  path: "/meetings" | "/skills" | "/knowledge" | "/connectors";
  icon: typeof Video;
  count?: number;
}[] = [
  { key: "meetings", label: "开始会议", path: "/meetings", icon: Video },
  {
    key: "skills",
    label: "技能安装",
    path: "/skills",
    icon: Package,
    count: SKILLS.filter((s) => s.status === "installed").length,
  },
  { key: "knowledge", label: "知识库", path: "/knowledge", icon: BookOpen },
  {
    key: "connectors",
    label: "连接器",
    path: "/connectors",
    icon: Plug,
    count: CONNECTORS.filter((c) => c.status === "connected").length,
  },
];

// Agent 列表实际由当前用户所属部门动态生成（示例：通用 + 产品）；默认路由即通用 Agent
const AGENT_NAV: { id: AgentId; label: string; path: "/" | "/product"; icon: typeof Bot }[] = [
  { id: "general", label: "通用 Agent", path: "/", icon: Bot },
  { id: "product", label: "产品 Agent", path: "/product", icon: Boxes },
];

export function ThreadListSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { pathname } = useLocation();

  return (
    <Sidebar {...props}>
      <SidebarHeader className="aui-sidebar-header mb-2 border-b">
        <div className="aui-sidebar-header-content flex items-center justify-between">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" render={<Link to="/" />}>
                <div className="aui-sidebar-header-icon-wrapper bg-sidebar-primary text-sidebar-primary-foreground flex aspect-square size-8 items-center justify-center rounded-lg">
                  <Sparkles className="aui-sidebar-header-icon size-4" />
                </div>
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
          <SidebarGroupLabel>我的空间</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {SPACE_NAV.map((item) => {
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.key}>
                    <SidebarMenuButton
                      isActive={pathname === item.path || pathname.startsWith(`${item.path}/`)}
                      render={<Link to={item.path} />}
                    >
                      <Icon />
                      <span>{item.label}</span>
                      {typeof item.count === "number" && item.count > 0 && (
                        <span className="bg-sidebar-primary text-sidebar-primary-foreground ml-auto flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] font-medium">
                          {item.count}
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
          <SidebarGroupLabel>我的 Agent</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {AGENT_NAV.map((item) => {
                const Icon = item.icon;
                return (
                  <SidebarMenuItem key={item.id}>
                    <SidebarMenuButton
                      isActive={pathname === item.path}
                      render={<Link to={item.path} />}
                    >
                      <Icon />
                      <span>{item.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>会话历史</SidebarGroupLabel>
          <SidebarGroupContent>
            <ThreadList />
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      {props.collapsible !== "none" && <SidebarRail />}
      <SidebarFooter className="aui-sidebar-footer border-t">
        <SidebarMenu>
          <SidebarMenuItem>
            <div className="flex items-center gap-2 px-2 py-2 text-xs text-sidebar-foreground/50">
              <Sparkles className="size-4" />
              <span>企业Agent平台 v0.1.0</span>
            </div>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
