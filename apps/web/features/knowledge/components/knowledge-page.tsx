"use client";

import { useState } from "react";
import { ArrowLeft, BookOpen, FileText, Plus, Upload, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  FILE_TYPE_META,
  KNOWLEDGE_BASES,
  type KnowledgeBase,
} from "@/features/knowledge/data/knowledge-data";

export function KnowledgePage() {
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);

  const selectedKb = KNOWLEDGE_BASES.find((kb) => kb.id === selectedKbId);

  if (selectedKb) {
    return <KnowledgeBaseDetail kb={selectedKb} onBack={() => setSelectedKbId(null)} />;
  }

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">知识库</h1>
          <p className="text-muted-foreground text-sm">
            建立自己的知识库，对话中使用 @ 选择知识库作为回答上下文
          </p>
        </div>
        <Button>
          <Plus className="size-4" />
          新建知识库
        </Button>
      </header>

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {KNOWLEDGE_BASES.map((kb) => (
          <li key={kb.id} className="flex flex-col gap-3 rounded-xl border bg-card p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="bg-muted text-muted-foreground flex size-9 items-center justify-center rounded-lg">
                <BookOpen className="size-4" />
              </div>
              <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
                {kb.owner}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{kb.name}</span>
              <span className="text-muted-foreground text-xs">{kb.description}</span>
            </div>
            <div className="text-muted-foreground flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1">
                <FileText className="size-3.5" />
                {kb.files.length} 个文件
              </span>
              <span>更新于 {kb.files[0]?.updatedAt}</span>
            </div>
            <Button
              variant="outline"
              size="sm"
              className="mt-auto w-fit"
              onClick={() => setSelectedKbId(kb.id)}
            >
              <Users className="size-3.5" />
              打开知识库
            </Button>
          </li>
        ))}
      </ul>

      <p className="text-muted-foreground text-xs">* 知识库列表与新建为 UI 骨架，功能待接入</p>
    </div>
  );
}

function KnowledgeBaseDetail({ kb, onBack }: { kb: KnowledgeBase; onBack: () => void }) {
  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-4" />
          返回知识库列表
        </Button>
      </div>

      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{kb.name}</h1>
            <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
              {kb.owner}
            </span>
          </div>
          <p className="text-muted-foreground text-sm">{kb.description}</p>
        </div>
        <Button>
          <Upload className="size-4" />
          上传文件
        </Button>
      </header>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-medium">
          <FileText className="text-muted-foreground size-4" />
          全部文件
          <span className="text-muted-foreground/60 text-xs">{kb.files.length} 个</span>
        </h2>
        <ul className="flex flex-col gap-2">
          {kb.files.map((file) => {
            const meta = FILE_TYPE_META[file.type];
            const Icon = meta.icon;
            return (
              <li
                key={file.id}
                className="flex items-center justify-between gap-4 rounded-xl border bg-card px-4 py-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="bg-muted text-muted-foreground flex size-9 shrink-0 items-center justify-center rounded-lg">
                    <Icon className="size-4" />
                  </div>
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate text-sm font-medium">{file.name}</span>
                    <span className="text-muted-foreground flex items-center gap-2 text-xs">
                      <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px]">
                        {meta.label}
                      </span>
                      <span>{file.size}</span>
                      <span>{file.uploader} 上传</span>
                      <span>更新于 {file.updatedAt}</span>
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Button variant="ghost" size="sm">
                    查看
                  </Button>
                </div>
              </li>
            );
          })}
          {kb.files.length === 0 && (
            <li className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
              暂无文件，点击右上角上传
            </li>
          )}
        </ul>
      </section>

      <p className="text-muted-foreground text-xs">* 文件列表与上传为 UI 骨架，功能待接入</p>
    </div>
  );
}
