import type { RecordDocument, RecordVersion, Workspace } from "@/interfaces/meeting";
import { http } from "@/lib/http";

/** 构造会议纪要协作接口地址。 */
const path = (id: string) => `/api/meetings/${encodeURIComponent(id)}/record`;
/** 读取会议纪要协作文档。 */
export const getRecord = (id: string, share?: string) =>
  http.get<RecordDocument>(path(id), { params: { share_token: share } });
/** 通过分享令牌读取协作文档。 */
export const resolveRecordShare = (token: string) =>
  http.get<RecordDocument>(`/api/meetings/shared/records/${encodeURIComponent(token)}`);
/** 获取会议纪要的分享链接令牌。 */
export const shareRecord = (id: string) => http.post<{ token: string }>(`${path(id)}/share`);
/** 查询会议纪要的历史版本。 */
export const listRecordVersions = (id: string, share?: string) =>
  http.get<RecordVersion[]>(`${path(id)}/versions`, { params: { share_token: share } });
/** 读取指定历史版本的内容。 */
export const getRecordVersion = (id: string, version: string, share?: string) =>
  http.get<{ state: string }>(`${path(id)}/versions/${version}`, {
    params: { share_token: share },
  });
/** 创建会议纪要版本快照。 */
export const checkpointRecord = (id: string, label: string) =>
  http.post(`${path(id)}/versions`, { label });
/** 将会议纪要恢复到指定版本。 */
export const restoreRecord = (id: string, version: string, revision: number) =>
  http.post<RecordDocument>(`${path(id)}/versions/${version}/restore`, {
    expected_revision: revision,
  });

/** 将会议纪要归档到指定知识库。 */
export const archiveMinutes = (id: string, baseId: number) =>
  http.post<Workspace>(`/api/meetings/${encodeURIComponent(id)}/minutes/archive`, {
    knowledge_base_id: baseId,
  });
