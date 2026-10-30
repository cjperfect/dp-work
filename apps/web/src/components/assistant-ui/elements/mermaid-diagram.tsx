import type { SyntaxHighlighterProps } from "@assistant-ui/react-markdown";
import { useEffect, useId, useState, type FC } from "react";

/**
 * Mermaid 图表（对应 assistant-ui mermaid-diagram 元素）：
 * 将 markdown 代码块中的 mermaid 语法渲染为 SVG 图表。
 * 通过 MarkdownTextPrimitive 的 componentsByLanguage 按语言接入：
 * `{ mermaid: { SyntaxHighlighter: MermaidDiagram } }`。
 * mermaid 库体积较大，使用动态 import 按需加载（仅出现 mermaid 代码块时引入）。
 */
export const MermaidDiagram: FC<SyntaxHighlighterProps> = ({ code }) => {
  const rawId = useId();
  const chartId = `aui-mermaid-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;
  const [svg, setSvg] = useState("");
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg("");
    setError(false);

    import("mermaid").then((mermaidModule) => {
      const mermaid = mermaidModule.default;
      mermaid.initialize({ startOnLoad: false, securityLevel: "strict" });
      return mermaid
        .render(chartId, code)
        .then(({ svg: rendered }) => {
          if (!cancelled) setSvg(rendered);
        })
        .catch(() => {
          if (!cancelled) setError(true);
        });
    });

    return () => {
      cancelled = true;
    };
  }, [chartId, code]);

  if (svg) {
    return (
      <div
        className="aui-mermaid-root my-3 flex justify-center overflow-x-auto py-2 [&_svg]:max-w-full [&_svg]:h-auto"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  }

  return (
    <pre className="border-border/50 bg-muted/30 my-3 overflow-x-auto rounded-xl border p-3.5 text-[13px] leading-relaxed">
      <code>{code}</code>
      {error && (
        <span className="text-destructive mt-2 block text-xs">
          图表渲染失败，已显示原文（请检查 Mermaid 语法）
        </span>
      )}
    </pre>
  );
};
