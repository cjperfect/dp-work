import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import { useEffect, useState, type FC } from "react";
import { createHighlighter, type Highlighter } from "shiki";

let highlighterPromise: Promise<Highlighter> | null = null;

function getHighlighter(): Promise<Highlighter> {
  highlighterPromise ??= createHighlighter({
    themes: ["github-dark"],
    langs: [
      "bash",
      "css",
      "html",
      "javascript",
      "jsx",
      "json",
      "markdown",
      "python",
      "sql",
      "typescript",
      "tsx",
      "xml",
      "yaml",
    ],
  });
  return highlighterPromise;
}

/**
 * Shiki 语法高亮（对应 assistant-ui shiki-highlighter 元素）：
 * 基于 Shiki（VS Code 同款高亮引擎）渲染代码块，按需加载主题与语言（单例）。
 * 通过 MarkdownTextPrimitive 的 SyntaxHighlighter 组件接入。
 */
export const ShikiHighlighter: FC<SyntaxHighlighterProps> = ({ language, code }) => {
  const [html, setHtml] = useState("");

  useEffect(() => {
    let cancelled = false;
    const lang = (language?.trim() || "text") as never;
    getHighlighter()
      .then((h) => h.codeToHtml(code, { lang, theme: "github-dark" }))
      .then((out) => {
        if (!cancelled) setHtml(out);
      })
      .catch(() => {
        if (!cancelled) setHtml("");
      });
    return () => {
      cancelled = true;
    };
  }, [code, language]);

  return (
    <div className="aui-shiki-root mb-3 overflow-hidden rounded-b-xl">
      {html ? (
        <div
          className="[&_pre]:border-border/50 [&_pre]:bg-[#0d1117] [&_pre]:overflow-x-auto [&_pre]:rounded-t-none [&_pre]:rounded-b-xl [&_pre]:border [&_pre]:border-t-0 [&_pre]:p-3.5 [&_pre]:text-[13px] [&_pre]:leading-relaxed"
          dangerouslySetInnerHTML={{ __html: html }}
        />
      ) : (
        <pre className="border-border/50 bg-muted/30 rounded-b-xl border border-t-0 p-3.5 text-[13px] leading-relaxed">
          <code>{code}</code>
        </pre>
      )}
    </div>
  );
};
