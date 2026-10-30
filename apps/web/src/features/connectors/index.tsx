import {
  CheckCircle2,
  ExternalLink,
  Loader2,
  Plug,
  PlugZap,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { useConnectorPage } from "./hooks/use-connector-page";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { UPCOMING_CONNECTORS } from "@/constants/connectors";

export function ConnectorsPage() {
  const {
    connectors,
    feishu,
    loading,
    error,
    reload,
    owner,
    disconnectOpen,
    setDisconnectOpen,
    busy,
    notice,
    flow,
    waiting,
    act,
  } = useConnectorPage();

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">连接器</h1>
          <p className="text-sm text-muted-foreground">连接外部服务，先完成账号授权与连接验证。</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={loading || !!busy}
          onClick={() => void reload()}
        >
          <RefreshCw className={loading ? "size-3.5 animate-spin" : "size-3.5"} />
          刷新状态
        </Button>
      </header>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {notice?.owner === owner && (
        <p
          role={notice.failed ? "alert" : "status"}
          className={`text-sm ${notice.failed ? "text-destructive" : "text-emerald-600"}`}
        >
          {notice.text}
        </p>
      )}

      <section className="flex flex-col gap-3">
        {connectors.map((connector) => {
          const connected = connector.status === "connected";
          const label = !feishu
            ? "读取中"
            : !feishu.installed
              ? "未安装"
              : !feishu.configured
                ? "未配置"
                : connected
                  ? "已连接"
                  : "未授权";
          return (
            <div key={connector.id} className="rounded-xl border bg-card p-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <div className="flex items-center gap-2">
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground">
                      <Plug className="size-4" />
                    </div>
                    <span className="text-sm font-medium">{connector.name}</span>
                    <span
                      className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${connected ? "bg-emerald-500/10 text-emerald-600" : "bg-muted text-muted-foreground"}`}
                    >
                      {connected ? (
                        <CheckCircle2 className="size-3" />
                      ) : (
                        <XCircle className="size-3" />
                      )}
                      {label}
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{connector.description}</p>
                  <div className="flex flex-wrap gap-1.5">
                    {connector.capabilities.map((cap) => (
                      <span
                        key={cap}
                        className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                  {connected && connector.account && (
                    <p className="text-xs text-muted-foreground">当前账号：{connector.account}</p>
                  )}
                  {connected && (
                    <p className="text-xs text-muted-foreground">
                      授权已保存在本机，下次打开自动恢复，无需重复扫码。
                    </p>
                  )}
                  {feishu && !feishu.installed && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      请在项目终端运行 <code>pnpm setup:feishu-cli</code> 后刷新。
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {feishu?.configured && (
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!!busy || waiting}
                      onClick={() => void act("verify")}
                    >
                      {busy === "verify" ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <CheckCircle2 className="size-3.5" />
                      )}
                      验证连接
                    </Button>
                  )}
                  {connected ? (
                    <Popover
                      open={disconnectOpen}
                      onOpenChange={(open) => {
                        if (!busy) setDisconnectOpen(open);
                      }}
                    >
                      <PopoverTrigger
                        render={
                          <Button variant="outline" size="sm" disabled={!!busy || waiting}>
                            <XCircle className="size-3.5" />
                            断开连接
                          </Button>
                        }
                      />
                      <PopoverContent align="end" className="w-64 p-3">
                        <p className="text-sm font-medium">断开本机飞书登录？</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          保留应用配置。此操作不会撤销飞书授权管理中的全部授权。
                        </p>
                        <div className="mt-3 flex justify-end gap-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            disabled={!!busy}
                            onClick={() => setDisconnectOpen(false)}
                          >
                            取消
                          </Button>
                          <Button
                            variant="destructive"
                            size="sm"
                            disabled={!!busy}
                            onClick={() => void act("disconnect")}
                          >
                            断开连接
                          </Button>
                        </div>
                      </PopoverContent>
                    </Popover>
                  ) : (
                    <Button
                      size="sm"
                      disabled={!feishu?.installed || !!busy || waiting}
                      onClick={() => void act(feishu?.configured ? "login" : "configure")}
                    >
                      {busy || waiting ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <PlugZap className="size-3.5" />
                      )}
                      {waiting ? "等待完成" : feishu?.configured ? "授权登录" : "配置飞书应用"}
                    </Button>
                  )}
                </div>
              </div>
              {flow && (
                <div className="mt-4 border-t pt-4" aria-live="polite">
                  {waiting ? (
                    <div className="flex flex-col gap-3">
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm font-medium">
                          {flow.action === "configure"
                            ? "第一步：配置飞书应用"
                            : "第二步：授权飞书账号"}
                        </p>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!!busy}
                          onClick={() => void act("cancel")}
                        >
                          取消授权
                        </Button>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {flow.action === "configure"
                          ? "由你在飞书官方页面完成应用配置；完成后返回这里继续授权登录。"
                          : "本次仅申请身份识别和保持登录权限，不包含文档、消息等业务权限。"}
                      </p>
                      {flow.url ? (
                        <a
                          href={flow.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex w-fit items-center gap-1 text-sm text-primary underline underline-offset-4"
                        >
                          打开飞书官方授权页面
                          <ExternalLink className="size-3.5" />
                        </a>
                      ) : (
                        <p className="text-sm text-muted-foreground">正在获取官方授权链接…</p>
                      )}
                      {flow.qr_code && (
                        <div className="flex w-fit flex-col items-center gap-2">
                          <img
                            src={flow.qr_code}
                            alt="飞书授权二维码"
                            width={192}
                            height={192}
                            className="rounded-lg border bg-white p-2"
                          />
                          <p className="text-xs text-muted-foreground">请使用飞书 App 扫描二维码</p>
                        </div>
                      )}
                      <p className="text-xs text-muted-foreground">
                        等待网页操作完成，状态会自动更新。链接失效后可取消并重新发起。
                      </p>
                    </div>
                  ) : (
                    <p
                      role={flow.state === "failed" ? "alert" : "status"}
                      className={`text-sm ${flow.state === "failed" ? "text-destructive" : "text-muted-foreground"}`}
                    >
                      {flow.message}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="flex items-center gap-1.5 text-sm font-medium">
          <Plug className="size-4 text-muted-foreground" />
          即将接入
        </h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {UPCOMING_CONNECTORS.map((item) => (
            <div
              key={item.name}
              className="flex flex-col gap-1 rounded-xl border border-dashed px-4 py-3.5 text-muted-foreground"
            >
              <span className="text-sm font-medium">{item.name}</span>
              <span className="text-xs">{item.description}</span>
            </div>
          ))}
        </div>
      </section>
      <p className="text-xs text-muted-foreground">
        当前仅提供 CLI 配置、用户授权与验证，业务同步和 Agent 执行后续接入。
      </p>
    </div>
  );
}
