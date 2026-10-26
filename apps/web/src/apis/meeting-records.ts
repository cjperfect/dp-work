import type { Workspace } from "./meetings";
import { request } from "@/lib/http";

export type RecordDocument = {
  meeting_id: string;
  title: string;
  owner: boolean;
  editable: boolean;
  content: string;
  state: string;
  epoch: string;
  revision: number;
  saved_revision?: number;
  saved_at?: string;
  updated_at: string;
};
export type RecordVersion = {
  id: string;
  revision: number;
  label: string;
  author: string;
  created_at: string;
};
const path = (id: string) => `/api/meetings/${encodeURIComponent(id)}/record`;
export const getRecord = (id: string, share?: string) =>
  request<RecordDocument>(path(id), { params: { share_token: share } });
export const resolveRecordShare = (token: string) =>
  request<RecordDocument>(`/api/meetings/shared/records/${encodeURIComponent(token)}`);
export const shareRecord = (id: string) =>
  request<{ token: string }>(`${path(id)}/share`, { method: "POST" });
export const listRecordVersions = (id: string, share?: string) =>
  request<RecordVersion[]>(`${path(id)}/versions`, { params: { share_token: share } });
export const getRecordVersion = (id: string, version: string, share?: string) =>
  request<{ state: string }>(`${path(id)}/versions/${version}`, { params: { share_token: share } });
export const checkpointRecord = (id: string, label: string) =>
  request(`${path(id)}/versions`, { method: "POST", data: { label } });
export const restoreRecord = (id: string, version: string, revision: number) =>
  request<RecordDocument>(`${path(id)}/versions/${version}/restore`, {
    method: "POST",
    data: { expected_revision: revision },
  });

export const archiveMinutes = (id: string, baseId: number) =>
  request<Workspace>(`/api/meetings/${encodeURIComponent(id)}/minutes/archive`, {
    method: "POST",
    data: { knowledge_base_id: baseId },
  });
