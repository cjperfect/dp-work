"""Electron 子进程 JSON-RPC：每行一条消息，stdout 仅用于协议。"""
import asyncio
import base64
import json
import os
import sys

from pydantic import ValidationError
from .protocol import METHODS, CONTROL, LIMITS, ERRORS
from . import handlers

MAX_LINE = LIMITS["maxInputLineBytes"]

class StdioServer:
    """按请求 ID 管理并发、流式通知与取消。"""

    def __init__(self, state, output, ready=lambda: True):
        self.state = state
        self.output = output
        self.ready = ready
        self.tasks = {}
        self.lock = asyncio.Lock()

    async def emit(self, message):
        data = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        async with self.lock:
            await asyncio.to_thread(self._write, data)

    def _write(self, data):
        self.output.write(data)
        self.output.flush()

    async def error(self, key, code, message):
        await self.emit({"jsonrpc": "2.0", "id": key, "error": {"code": code, "message": message}})

    async def handle(self, raw):
        """校验请求并调度，不阻塞后续取消或健康检查。"""
        try:
            message = json.loads(raw)
        except (ValueError, UnicodeError):
            await self.error(None, ERRORS["parse"], "JSON 格式错误。")
            return
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            await self.error(None, ERRORS["invalidRequest"], "无效的 JSON-RPC 请求。")
            return
        key = message.get("id")
        method = message.get("method")
        if method == CONTROL["cancel"] and key is None:
            params = message.get("params")
            target = params.get("id") if isinstance(params, dict) else None
            if isinstance(target, str) and target in self.tasks:
                self.tasks[target].cancel()
            return
        if not isinstance(key, str) or not key or len(key) > 128:
            await self.error(None, ERRORS["invalidRequest"], "请求 ID 无效。")
            return
        if key in self.tasks:
            # 同一个 ID 的第二个响应会破坏首个请求的关联，直接忽略重复帧。
            return
        if method == CONTROL["health"]:
            await self.emit({"jsonrpc": "2.0", "id": key, "result": {
                "ok": self.ready(), "service": "dp-work-sidecar",
                "instance_id": os.environ.get("DP_SIDECAR_INSTANCE_ID"),
            }})
            return
        if not isinstance(method, str) or method not in METHODS:
            await self.error(key, ERRORS["methodNotFound"], "不支持的方法。")
            return
        if len(self.tasks) >= LIMITS["maxConcurrentCalls"]:
            await self.error(key, ERRORS["busy"], "Sidecar 并发任务超限。")
            return
        task = asyncio.create_task(self.execute(key, method, message.get("params")))
        self.tasks[key] = task
        task.add_done_callback(lambda _: self.tasks.pop(key, None))

    async def execute(self, key, method, params):
        """按方法名直接调用业务函数，并推送流式内容。"""
        seq = 0

        async def head(status, content_type):
            await self.emit({"jsonrpc": "2.0", "method": CONTROL["head"], "params": {
                "id": key, "status": status, "content_type": content_type}})

        async def chunk(data):
            nonlocal seq
            for offset in range(0, len(data), LIMITS["chunkBytes"]):
                await self.emit({"jsonrpc": "2.0", "method": CONTROL["chunk"], "params": {
                    "id": key, "seq": seq,
                    "data": base64.b64encode(data[offset:offset + LIMITS["chunkBytes"]]).decode()}})
                seq += 1

        try:
            if not isinstance(params, dict):
                await self.error(key, ERRORS["invalidParams"], "调用参数必须为对象。")
                return
            try:
                result = await handlers.dispatch(method, params, self.state)
            except handlers.OperationError as cause:
                await head(cause.status, "application/json")
                await chunk(json.dumps({"detail": cause.detail}, ensure_ascii=False).encode())
            else:
                if isinstance(result, handlers.EventStream):
                    await head(200, "text/event-stream")
                    async for event in result.events:
                        await chunk(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                else:
                    await head(200, "application/json")
                    await chunk(json.dumps(result, ensure_ascii=False).encode())
            await self.emit({"jsonrpc": "2.0", "id": key, "result": {"complete": True}})
        except ValidationError:
            await self.error(key, ERRORS["invalidParams"], "业务参数校验失败。")
        except asyncio.CancelledError:
            await self.error(key, ERRORS["cancelled"], "任务已取消。")
        except Exception:
            await self.error(key, ERRORS["internal"], "Sidecar 执行失败，请检查日志。")

    async def close(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def serve(self, source):
        """读取有长度限制的 JSONL；父进程关闭管道后停止所有任务。"""
        try:
            if os.name != "nt":
                reader = asyncio.StreamReader(limit=MAX_LINE)
                protocol = asyncio.StreamReaderProtocol(reader)
                transport, _ = await asyncio.get_running_loop().connect_read_pipe(lambda: protocol, source)
                try:
                    while raw := await reader.readline():
                        await self.handle(raw)
                finally:
                    transport.close()
            else:
                while raw := await asyncio.to_thread(source.readline, MAX_LINE + 1):
                    if len(raw) > MAX_LINE:
                        raise ValueError("JSON-RPC 消息过大。")
                    await self.handle(raw)
        finally:
            await self.close()


def main():
    """标准输出留给协议，其他 print 和日志重定向到 stderr。"""
    output = sys.stdout.buffer
    sys.stdout = sys.stderr
    import uvicorn
    from src.main import app
    from src.config import PORT

    async def run():
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
        rpc = StdioServer(app.state, output, lambda: server.started and not server.should_exit)
        http_task = asyncio.create_task(server.serve())
        io_task = asyncio.create_task(rpc.serve(sys.stdin.buffer))
        try:
            done, _ = await asyncio.wait((http_task, io_task), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            server.should_exit = True
            io_task.cancel()
            await asyncio.gather(io_task, return_exceptions=True)
            await http_task

    asyncio.run(run())


if __name__ == "__main__":
    main()
