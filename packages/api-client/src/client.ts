/**
 * @dp-work/api-client —— 桌面端与 Web 共用的 TS API 客户端
 *
 * 封装 api 服务（services/api）的转写分句批量上行，浏览器与 Node/Electron 通用。
 */
import { SegmentsBatch, SegmentsBatchResult, SYNC_API } from "@dp-work/contracts";

export interface ApiClientOptions {
  /** api 服务地址，默认 http://localhost:8000 */
  baseUrl?: string;
  /** 请求超时（毫秒），默认 15000 */
  timeoutMs?: number;
}

export class ApiClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://localhost:8000").replace(/\/$/, "");
    this.timeoutMs = options.timeoutMs ?? 15000;
  }

  /**
   * 批量上行转写分句（幂等：重复 id 被服务端忽略）。
   * 返回服务端实际写入数与忽略数；网络/5xx 抛错（由调用方保留 pending 重试）。
   */
  async pushSegments(batch: SegmentsBatch): Promise<SegmentsBatchResult> {
    const { segmentsPath, batchSize } = SYNC_API;
    if (batch.segments.length > batchSize) {
      throw new Error(`单批最多 ${batchSize} 条分句，当前 ${batch.segments.length}`);
    }

    const res = await fetch(`${this.baseUrl}${segmentsPath}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        meeting_id: batch.meetingId,
        segments: batch.segments.map((s) => ({
          id: s.id,
          seq: s.seq,
          speaker: s.speaker ?? null,
          text: s.text,
          start_ms: s.startMs ?? null,
          end_ms: s.endMs ?? null,
        })),
      }),
      signal: AbortSignal.timeout(this.timeoutMs),
    });

    if (!res.ok) {
      throw new Error(`api ${segmentsPath} 返回 ${res.status}`);
    }
    return (await res.json()) as SegmentsBatchResult;
  }

  /** 健康检查 */
  async health(): Promise<boolean> {
    try {
      const res = await fetch(`${this.baseUrl}/health`, {
        signal: AbortSignal.timeout(3000),
      });
      return res.ok;
    } catch {
      return false;
    }
  }
}

export const defaultClient = new ApiClient();
