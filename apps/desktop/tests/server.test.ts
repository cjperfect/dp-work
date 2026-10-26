import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import http, { type Server } from "node:http";
import { test } from "node:test";
import { startWebServer } from "../src/server";

async function close(server: Server) {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
}

test("desktop serves SPA routes and assets without exposing files outside the build", async () => {
  const temporary = await mkdtemp(path.join(tmpdir(), "dp-static-"));
  let server: Server | undefined;
  try {
    const root = path.join(temporary, "web");
    await mkdir(path.join(root, "assets"), { recursive: true });
    await writeFile(path.join(root, "index.html"), "<main>app-shell</main>");
    await writeFile(path.join(root, "assets/app.js"), "console.log('app')");
    await writeFile(path.join(temporary, "private.txt"), "private");
    await symlink(path.join(temporary, "private.txt"), path.join(root, "private.txt"));
    server = await startWebServer(root, 0);
    const base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
    assert.equal(
      await (await fetch(`${base}/knowledge/server-1`)).text(),
      "<main>app-shell</main>",
    );
    const script = await fetch(`${base}/assets/app.js`);
    assert.equal(script.status, 200);
    assert.match(script.headers.get("Content-Type")!, /javascript/);
    assert.equal((await fetch(`${base}/assets/missing.js`)).status, 404);
    assert.equal((await fetch(`${base}/.env`)).status, 403);
    assert.equal((await fetch(`${base}/private.txt`)).status, 403);
    assert.equal(
      (await fetch(`${base}/assets/app.js`, { method: "HEAD" })).headers.get("Content-Length"),
      "18",
    );
    assert.equal((await fetch(`${base}/`, { method: "POST" })).status, 405);
  } finally {
    if (server) await close(server);
    await rm(temporary, { recursive: true, force: true });
  }
});

test("desktop proxies authenticated JSON requests and preserves backend status", async () => {
  const temporary = await mkdtemp(path.join(tmpdir(), "dp-proxy-"));
  let server: Server | undefined;
  const api = http.createServer((request, response) => {
    let body = "";
    request.on("data", (chunk) => {
      body += chunk;
    });
    request.on("end", () => {
      response.writeHead(409, { "Content-Type": "application/json" });
      response.end(
        JSON.stringify({
          path: request.url,
          authorization: request.headers.authorization,
          body: JSON.parse(body),
        }),
      );
    });
  });
  try {
    await writeFile(path.join(temporary, "index.html"), "shell");
    await new Promise<void>((resolve) => api.listen(0, "127.0.0.1", resolve));
    server = await startWebServer(
      temporary,
      0,
      `http://127.0.0.1:${(api.address() as { port: number }).port}`,
    );
    const base = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
    const result = await fetch(`${base}/api/knowledge-bases?q=test`, {
      method: "POST",
      headers: { Authorization: "Bearer fixture", "Content-Type": "application/json" },
      body: JSON.stringify({ name: "资料" }),
    });
    assert.equal(result.status, 409);
    assert.deepEqual(await result.json(), {
      path: "/api/knowledge-bases?q=test",
      authorization: "Bearer fixture",
      body: { name: "资料" },
    });
    await close(api);
    assert.equal((await fetch(`${base}/api/knowledge-bases`)).status, 502);
  } finally {
    if (server) await close(server);
    if (api.listening) await close(api);
    await rm(temporary, { recursive: true, force: true });
  }
});

for (const socketPath of [
  "/api/meetings/events",
  "/api/knowledge-bases/events",
  "/api/meetings/demo-record/record/events",
]) {
  test(`desktop forwards authenticated API WebSocket ${socketPath}`, async () => {
    const { createHash } = await import("node:crypto");
    const temporary = await mkdtemp(path.join(tmpdir(), "dp-ws-"));
    const api = http.createServer();
    const peers = new Set<import("node:stream").Duplex>();
    api.on("upgrade", (request, socket) => {
      peers.add(socket);
      socket.on("close", () => peers.delete(socket));
      assert.equal(request.url, socketPath);
      const accept = createHash("sha1")
        .update(request.headers["sec-websocket-key"] + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
        .digest("base64");
      socket.write(
        `HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`,
      );
      const payload = Buffer.from('{"type":"ping"}');
      socket.write(Buffer.concat([Buffer.from([0x81, payload.length]), payload]));
    });
    await new Promise<void>((resolve) => api.listen(0, "127.0.0.1", resolve));
    let server: Server | undefined;
    let socket: WebSocket | undefined;
    try {
      await writeFile(path.join(temporary, "index.html"), "<main>app</main>");
      server = await startWebServer(
        temporary,
        0,
        `http://127.0.0.1:${(api.address() as { port: number }).port}`,
      );
      socket = new WebSocket(
        `ws://127.0.0.1:${(server.address() as { port: number }).port}${socketPath}`,
      );
      const message = await new Promise<string>((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error("WebSocket proxy timed out")), 3000);
        socket!.onmessage = (event) => {
          clearTimeout(timer);
          resolve(String(event.data));
        };
        socket!.onerror = () => {
          clearTimeout(timer);
          reject(new Error("WebSocket proxy failed"));
        };
      });
      assert.equal(message, '{"type":"ping"}');
    } finally {
      socket?.close();
      for (const peer of peers) peer.destroy();
      if (server) await close(server);
      await close(api);
      await rm(temporary, { recursive: true, force: true });
    }
  });
}
