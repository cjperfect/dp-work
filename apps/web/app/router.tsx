"use client";

import { lastAssistantMessageIsCompleteWithToolCalls } from "ai";
import {
  Outlet,
  RouterProvider,
  createRootRoute,
  createRoute,
  createRouter,
  useLocation,
  Link,
} from "@tanstack/react-router";
import { useChatRuntime, AssistantChatTransport } from "@assistant-ui/ai-sdk";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useEffect } from "react";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { ThreadListSidebar } from "@/components/assistant-ui/elements/threadlist-sidebar.aui";
import { Separator } from "@/components/ui/separator";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";
import { MeetingsPage, MeetingSessionPage, MeetingMinutesPage } from "@/features/meetings";
import { SkillsPage } from "@/features/skills";
import { KnowledgePage } from "@/features/knowledge";
import { AgentPage, AGENTS } from "@/features/agent";
import { useAppStore } from "@/stores/app-store";
import type { AgentId } from "@/interfaces/app";

/** 路径 → 面包屑标题 */
const pathToTitle = (pathname: string): string => {
  if (pathname === "/") return AGENTS[0]?.name ?? "通用 Agent";
  if (pathname === "/product") {
    const agent = AGENTS.find((a) => a.id === "product");
    return agent?.name ?? "产品 Agent";
  }
  if (pathname.startsWith("/meetings")) return "开始会议";
  if (pathname.startsWith("/skills")) return "技能安装";
  if (pathname.startsWith("/knowledge")) return "知识库";
  return "会话";
};

/** 应用外壳：Provider + 侧边栏 + 内容区（路由布局） */
function AppShell() {
  const { pathname } = useLocation();
  const runtime = useChatRuntime({
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls,
    transport: new AssistantChatTransport({ api: "/api/chat" }),
  });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <SidebarProvider>
        <div className="flex h-dvh w-full pr-0.5">
          <ThreadListSidebar />
          <SidebarInset>
            <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
              <SidebarTrigger />
              <Separator orientation="vertical" className="mr-2 h-4" />
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbPage>企业Agent平台</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbItem>
                    <BreadcrumbPage className="text-muted-foreground">
                      {pathToTitle(pathname)}
                    </BreadcrumbPage>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </header>
            <div className="flex-1 overflow-hidden">
              <Outlet />
            </div>
          </SidebarInset>
        </div>
      </SidebarProvider>
    </AssistantRuntimeProvider>
  );
}

const rootRoute = createRootRoute({ component: AppShell });

/** Agent 聊天页：按路由确定 agentId 并同步到 store（线程归属/会话过滤依赖） */
function AgentRoute({ agentId }: { agentId: AgentId }) {
  const setAgentId = useAppStore((s) => s.setAgentId);

  useEffect(() => {
    setAgentId(agentId);
  }, [setAgentId, agentId]);

  return <AgentPage agentId={agentId} />;
}

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: () => <AgentRoute agentId="general" />,
});

const productRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/product",
  component: () => <AgentRoute agentId="product" />,
});

const meetingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/meetings",
  component: MeetingsPage,
});

const meetingActiveRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/meetings/active",
  component: MeetingSessionPage,
});

const meetingMinutesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/meetings/minutes",
  component: MeetingMinutesPage,
});

const skillsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/skills",
  component: SkillsPage,
});

const knowledgeRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/knowledge",
  component: KnowledgePage,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  productRoute,
  meetingsRoute,
  meetingActiveRoute,
  meetingMinutesRoute,
  skillsRoute,
  knowledgeRoute,
]);

export const router = createRouter({ routeTree });

export function AppRouter() {
  return <RouterProvider router={router} />;
}

export { Link };
