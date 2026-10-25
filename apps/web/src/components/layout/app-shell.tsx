import { Outlet, useMatches } from "@tanstack/react-router";
import { ChatRuntime } from "@/features/agent/components/chat-runtime";
import { AgentBootstrap } from "@/features/agent/components/agent-bootstrap";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { ThreadListSidebar } from "@/components/assistant-ui/elements/threadlist-sidebar.aui";
import { Separator } from "@/components/ui/separator";
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
} from "@/components/ui/breadcrumb";

export function AppShell() {
  const title = useMatches({
    select: (matches) =>
      matches
        .map((match) => match.staticData.title)
        .filter(Boolean)
        .at(-1) ?? "会话",
  });

  return (
    <>
      <AgentBootstrap />
      <SidebarProvider>
        <ChatRuntime>
          {/* min-h-0：防止内部会话内容把外层撑高超过屏幕高度 */}
          <div className="flex h-dvh min-h-0 w-full pr-0.5">
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
                      <BreadcrumbPage className="text-muted-foreground">{title}</BreadcrumbPage>
                    </BreadcrumbItem>
                  </BreadcrumbList>
                </Breadcrumb>
              </header>
              <div className="flex-1 overflow-hidden">
                <Outlet />
              </div>
            </SidebarInset>
          </div>
        </ChatRuntime>
      </SidebarProvider>
    </>
  );
}
