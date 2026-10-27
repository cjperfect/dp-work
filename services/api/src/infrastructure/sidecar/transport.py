"""保持 HTTPX 调用协议，通过用户设备的出站连接执行请求。"""
import anyio
import httpx
from src.core import config
from src.infrastructure.database.notifications import listen
from . import relay


class RelayStream(httpx.AsyncByteStream):
    def __init__(self, key, subscription, queue):
        self.key,self.subscription,self.queue,self.closed=key,subscription,queue,False

    async def __aiter__(self):
        seq=0
        while True:
            row,chunks=await relay.snapshot(self.key,seq)
            if not row or row.state in ('failed','cancelled'):
                raise relay.DeviceOffline('本机执行服务已断开，请重新连接。')
            for chunk in chunks:
                seq=chunk.seq+1
                yield chunk.data
            if row.state=='completed' and seq>=row.next_seq: return
            if not chunks: await relay.wait_signal(self.queue,self.key,row.deadline_at)

    async def aclose(self):
        if self.closed:return
        self.closed=True
        with anyio.CancelScope(shield=True):
            try: await relay.cancel(self.key)
            finally: await self.subscription.__aexit__(None,None,None)


class DeviceTransport(httpx.AsyncBaseTransport):
    def __init__(self,timeout): self.timeout=timeout
    async def handle_async_request(self,request):
        subscription=listen('device_responses')
        queue=await subscription.__aenter__()
        key=None
        try:
            key=await relay.create_call(request,self.timeout)
            while True:
                row,_=await relay.snapshot(key)
                if not row or row.state in ('failed','cancelled'):raise relay.DeviceOffline('本机执行服务已断开。')
                if row.status_code is not None:
                    return httpx.Response(row.status_code,headers={'Content-Type':row.response_type or 'application/json'},
                        stream=RelayStream(key,subscription,queue),request=request)
                await relay.wait_signal(queue,key,row.deadline_at)
        except BaseException:
            with anyio.CancelScope(shield=True):
                if key:await relay.cancel(key)
                await subscription.__aexit__(None,None,None)
            raise


def client(timeout=30, transport=None):
    """仅开发兼容模式直接连接；设备模式不访问云端回环端口。"""
    seconds=timeout.read if isinstance(timeout,httpx.Timeout) else timeout
    selected=transport if transport is not None else DeviceTransport(seconds or 210) if config.SIDECAR_TRANSPORT=='device' else None
    options={"timeout":timeout,"follow_redirects":False}
    if selected is not None: options["transport"]=selected
    return httpx.AsyncClient(**options)
