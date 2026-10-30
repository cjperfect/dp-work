import type { PartialBlock } from "@blocknote/core";
export type Meeting = {
  id: string;
  owner_id: number;
  title: string;
  scheduled_at: string;
  participants: string[];
  status: "active" | "paused" | "ended" | "archived";
  elapsed_ms: number;
  resumed_at: string | null;
  ended_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  minutes_status?: number | null;
  generation_status?: "idle" | "generating" | "ready" | "failed";
  generation_error?: string | null;
  generation_ready_at?: number | null;
  generation_task_id?: string | null;
  generation_source_revision?: number | null;
};

export type Entry = {
  id: string;
  revision?: number;
  seq: number;
  speaker: string | null;
  text: string;
  start_ms: number;
  end_ms?: number | null;
};

export type Workspace = {
  meeting: Meeting;
  segments: Entry[];
  minutes: {
    content: string;
    blocks?: PartialBlock[] | null;
    status: number;
    archived_document_id: number | string | null;
  } | null;
};

export type GenerationAccepted = {
  task_id: string;
  source_revision: number;
  meeting: Meeting;
};

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
