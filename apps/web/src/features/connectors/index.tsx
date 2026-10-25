import { useConnectors } from "@/stores/connectors";
import { useState } from "react";
import { CheckCircle2, Plug, PlugZap, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { UPCOMING_CONNECTORS } from "@/features/connectors/constants/connectors";

export function ConnectorsPage() {
  const { connectors, updateConnectors } = useConnectors();
  const [disconnectTarget, setDisconnectTarget] = useState<string | null>(null);

  const handleConnect = () => {
    // 连接授权流程待接入后端（OAuth / CLI 令牌）；先本地标记已连接
    updateConnectors((prev) =>
      prev.map((c) =>
        c.id === "lark-cli"
          ? { ...c, status: "connected", account: "chen.jiang@breo.com（飞书企业号）" }
          : c,
      ),
    );
  };

  const handleDisconnect = () => {
    if (!disconnectTarget) return;
    updateConnectors((prev) =>
      prev.map((c) =>
        c.id === disconnectTarget ? { ...c, status: "disconnected", account: undefined } : c,
      ),
    );
    setDisconnectTarget(null);
  };

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">连接器</h1>
        <p className="text-muted-foreground text-sm">
          连接外部服务（如飞书 CLI），让会议纪要、知识库资料与 Agent 输出可以双向同步，不再人工搬运
        </p>
      </header>

      <section className="flex flex-col gap-3">
        {connectors.map((connector) => {
          const connected = connector.status === "connected";
          return (
            <div
              key={connector.id}
              className="flex items-start justify-between gap-4 rounded-xl border bg-card px-4 py-4"
            >
              <div className="flex min-w-0 flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <div className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
                    <Plug className="size-4" />
                  </div>
                  <span className="text-sm font-medium">{connector.name}</span>
                  <span
                    className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${
                      connected
                        ? "bg-emerald-500/10 text-emerald-600"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {connected ? (
                      <CheckCircle2 className="size-3" />
                    ) : (
                      <XCircle className="size-3" />
                    )}
                    {connected ? "已连接" : "未连接"}
                  </span>
                </div>
                <p className="text-muted-foreground text-sm">{connector.description}</p>
                <div className="flex flex-wrap items-center gap-1.5">
                  {connector.capabilities.map((cap) => (
                    <span
                      key={cap}
                      className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-xs"
                    >
                      {cap}
                    </span>
                  ))}
                </div>
                {connected && connector.account && (
                  <p className="text-muted-foreground text-xs">当前账号：{connector.account}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {connected ? (
                  <Popover
                    open={disconnectTarget === connector.id}
                    onOpenChange={(open) => {
                      setDisconnectTarget(open ? connector.id : null);
                    }}
                  >
                    <PopoverTrigger
                      render={
                        <Button variant="outline" size="sm">
                          <XCircle className="size-3.5" />
                          断开连接
                        </Button>
                      }
                    />
                    <PopoverContent align="end" className="w-64 p-3">
                      <p className="text-sm font-medium">断开连接</p>
                      <p className="text-muted-foreground mt-1 text-xs">
                        断开后会议纪要、知识库资料将不再自动同步到飞书，确定要断开吗？
                      </p>
                      <div className="mt-3 flex justify-end gap-2">
                        <Button variant="ghost" size="sm" onClick={() => setDisconnectTarget(null)}>
                          取消
                        </Button>
                        <Button variant="destructive" size="sm" onClick={handleDisconnect}>
                          断开连接
                        </Button>
                      </div>
                    </PopoverContent>
                  </Popover>
                ) : (
                  <Button size="sm" onClick={handleConnect}>
                    <PlugZap className="size-3.5" />
                    连接
                  </Button>
                )}
              </div>
            </div>
          );
        })}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-medium">
          <Plug className="text-muted-foreground size-4" />
          即将接入
        </h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {UPCOMING_CONNECTORS.map((item) => (
            <div
              key={item.name}
              className="text-muted-foreground flex flex-col gap-1 rounded-xl border border-dashed px-4 py-3.5"
            >
              <span className="text-sm font-medium">{item.name}</span>
              <span className="text-xs">{item.description}</span>
            </div>
          ))}
        </div>
      </section>

      <p className="text-muted-foreground text-xs">
        * 当前为模拟连接，操作结果保存在此浏览器，不会连接外部服务
      </p>
    </div>
  );
}
