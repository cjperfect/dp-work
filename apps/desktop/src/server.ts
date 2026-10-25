import { createReadStream, existsSync } from "node:fs";
import { realpath, stat } from "node:fs/promises";
import http, { type IncomingMessage, type ServerResponse, type Server } from "node:http";
import https from "node:https";
import path from "node:path";
import { pipeline } from "node:stream";
import { setTimeout as delay } from "node:timers/promises";
import { apiBaseUrl } from "./config";

const mime: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".wasm": "application/wasm",
  ".pdf": "application/pdf",
};

/** 等待开发服务可访问。 */
export async function waitForWeb(
  url: string,
  stopped: () => boolean,
  timeout = 90_000,
): Promise<void> {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline && !stopped()) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(1500) });
      await response.body?.cancel();
      if (response.status < 500) return;
    } catch {
      // 服务启动期间继续等待。
    }
    await delay(300);
  }
  throw new Error("Web 服务未能启动，请检查终端日志。");
}

function reply(response: ServerResponse, status: number, message: string): void {
  if (response.headersSent) {
    response.destroy();
    return;
  }
  response.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  response.end(JSON.stringify({ code: 5000, message, data: null }));
}

function forwardedHeaders(headers: http.IncomingHttpHeaders): http.OutgoingHttpHeaders {
  const result = { ...headers };
  const excluded = [
    "host",
    "connection",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
    "upgrade",
    "te",
    "trailer",
    "proxy-authorization",
    "proxy-authenticate",
    ...(headers.connection?.split(",") ?? []),
  ];
  for (const key of excluded) delete result[key.trim().toLowerCase()];
  return result;
}

/** 转发业务 API 请求。 */
function proxyApi(request: IncomingMessage, response: ServerResponse, base: string): void {
  const target = new URL(base.replace(/\/$/, "") + request.url);
  const upstream = (target.protocol === "https:" ? https : http).request(
    target,
    {
      method: request.method,
      headers: { ...forwardedHeaders(request.headers), host: target.host },
    },
    (result) => {
      response.writeHead(result.statusCode ?? 502, forwardedHeaders(result.headers));
      pipeline(result, response, () => {});
    },
  );
  upstream.setTimeout(30_000, () => upstream.destroy(new Error("API 请求超时。")));
  upstream.on("error", () => reply(response, 502, "无法连接 API 服务，请确认后端已启动。"));
  request.on("aborted", () => upstream.destroy());
  response.on("close", () => {
    if (!response.writableEnded) upstream.destroy();
  });
  pipeline(request, upstream, () => {});
}

/** 提供静态资源、页面路由回退和 API 代理。 */
export async function startWebServer(
  root: string,
  port: number,
  apiBase = "http://127.0.0.1:8000",
): Promise<Server> {
  const base = apiBaseUrl(apiBase);
  if (!existsSync(path.join(root, "index.html")))
    throw new Error("缺少 Web 构建产物，请先运行 pnpm --filter @dp-work/desktop build:web。");
  const directory = await realpath(root);
  const server = http.createServer((request, response) => {
    void (async () => {
      const expectedHosts = new Set([
        `127.0.0.1:${(server.address() as { port: number }).port}`,
        `localhost:${(server.address() as { port: number }).port}`,
      ]);
      if (!expectedHosts.has(request.headers.host ?? "")) {
        reply(response, 403, "无效的请求来源。");
        return;
      }
      const url = new URL(request.url ?? "/", "http://localhost");
      if (url.pathname === "/api" || url.pathname.startsWith("/api/")) {
        proxyApi(request, response, base);
        return;
      }
      if (request.method !== "GET" && request.method !== "HEAD") {
        reply(response, 405, "不支持的请求方法。");
        return;
      }
      let pathname: string;
      try {
        pathname = decodeURIComponent(url.pathname);
      } catch {
        reply(response, 400, "无效的路径。");
        return;
      }
      if (
        pathname.includes("\0") ||
        pathname.includes("\\") ||
        pathname.split("/").some((part) => part.startsWith("."))
      ) {
        reply(response, 403, "无效的路径。");
        return;
      }
      let file = path.resolve(directory, `.${pathname}`);
      if (!file.startsWith(directory + path.sep) && file !== directory) {
        reply(response, 403, "无效的路径。");
        return;
      }
      let info = await stat(file).catch(() => null);
      if (!info?.isFile()) {
        if (path.extname(pathname) || pathname.startsWith("/assets/")) {
          reply(response, 404, "文件不存在。");
          return;
        }
        file = path.join(directory, "index.html");
        info = await stat(file);
      }
      const resolved = await realpath(file);
      if (!resolved.startsWith(directory + path.sep)) {
        reply(response, 403, "无效的路径。");
        return;
      }
      response.writeHead(200, {
        "Content-Type": mime[path.extname(file)] ?? "application/octet-stream",
        "Content-Length": info.size,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": pathname.startsWith("/assets/")
          ? "public, max-age=31536000, immutable"
          : "no-cache",
      });
      if (request.method === "HEAD") response.end();
      else pipeline(createReadStream(resolved), response, () => {});
    })().catch(() => reply(response, 500, "页面加载失败。"));
  });
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", () => {
      server.off("error", reject);
      resolve();
    });
  });
  return server;
}
