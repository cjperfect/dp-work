import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";

import { useEffect, useRef } from "react";
import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import { zh } from "@blocknote/core/locales";
import type { BlockNoteEditor as Editor, PartialBlock } from "@blocknote/core";

export interface BlockNoteEditorProps {
  /** 初始文档块（会议纪要等场景从持久化恢复）；与 markdown 二选一，markdown 优先 */
  initialContent?: PartialBlock[] | null;
  /** 初始 Markdown 文本：挂载后解析为块并替换文档 */
  markdown?: string;
  /** 是否可编辑，默认 true；只读用于查看模式 */
  editable?: boolean;
  /** 文档变化回调，返回块数组（可用于持久化） */
  onChange?: (blocks: Record<string, unknown>[]) => void;
  /** 富文本变化时同时返回文档块与 Markdown，供持久化及导图使用。 */
  onDocumentChange?: (document: { blocks: PartialBlock[]; markdown: string }) => void;
  /** editor 实例就绪回调（供外部做程序化插入/更新） */
  onEditorReady?: (editor: Editor) => void;
  className?: string;
}

/** 共用富文本编辑器：BlockNote（中文界面），会议纪要实时转写与知识库解析结果共用 */
export function BlockNoteEditor({
  initialContent,
  markdown,
  editable = true,
  onChange,
  onDocumentChange,
  onEditorReady,
  className,
}: BlockNoteEditorProps) {
  const editor = useCreateBlockNote({
    dictionary: zh,
    // 仅在提供了有效初始块时恢复；否则用 BlockNote 默认空文档
    initialContent: initialContent && initialContent.length > 0 ? initialContent : undefined,
    // 扩展文字颜色样式（默认样式仅含背景色，无前景色）
    styleSchema: {
      color: {
        type: "string",
        default: "#000000",
        propSchema: "string",
      },
    },
  });

  const applying = useRef(markdown !== undefined);
  const lastMarkdown = useRef<string | undefined>(undefined);
  const lastBlocks = useRef(JSON.stringify(initialContent ?? null));

  useEffect(() => {
    onEditorReady?.(editor);
  }, [editor, onEditorReady]);

  useEffect(() => {
    if (markdown === undefined || markdown === lastMarkdown.current) return;
    applying.current = true;
    try {
      const blocks = markdown ? editor.tryParseMarkdownToBlocks(markdown) : [];
      editor.replaceBlocks(editor.document, blocks.length ? blocks : [{ type: "paragraph" }]);
      lastMarkdown.current = markdown;
      lastBlocks.current = JSON.stringify(editor.document);
    } finally {
      applying.current = false;
    }
  }, [editor, markdown]);

  useEffect(() => {
    if (markdown !== undefined || !initialContent) return;
    const next = JSON.stringify(initialContent);
    if (next === lastBlocks.current) return;
    applying.current = true;
    try {
      editor.replaceBlocks(
        editor.document,
        initialContent.length ? initialContent : [{ type: "paragraph" }],
      );
      lastBlocks.current = JSON.stringify(editor.document);
    } finally {
      applying.current = false;
    }
  }, [editor, initialContent, markdown]);

  return (
    <BlockNoteView
      editor={editor}
      theme="light"
      editable={editable}
      onChange={(ed) => {
        if (!editable || applying.current) return;
        const blocks = ed.document as PartialBlock[];
        lastBlocks.current = JSON.stringify(blocks);
        onChange?.(blocks as Record<string, unknown>[]);
        if (onDocumentChange) {
          const next = ed.blocksToMarkdownLossy();
          lastMarkdown.current = next;
          onDocumentChange({ blocks, markdown: next });
        }
      }}
      className={className}
    />
  );
}
