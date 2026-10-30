"use client";

import { Fragment, type ComponentProps, type ReactElement, type ReactNode } from "react";
import {
  ChevronDownIcon,
  FileIcon,
  FileCode2Icon,
  FileJsonIcon,
  FileTextIcon,
  FileImageIcon,
  FolderIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { mono, paper } from "./surfaces";
import { take } from "../utils/range";

export interface FileTreeNode {
  path: string;
  name: string;
  depth: number;
  kind: "folder" | "file";
  additions?: number;
  deletions?: number;
}

/** 用图标形状和颜色区分目录及常见文件类型。 */
function FileTypeIcon({ path }: { path: string }) {
  const extension = path.split(/[\\/]/).at(-1)?.split(".").at(-1)?.toLowerCase();
  let Icon = FileIcon;
  let color = "text-slate-500 dark:text-slate-400";
  if (["js", "jsx", "mjs", "cjs"].includes(extension ?? "")) {
    Icon = FileCode2Icon;
    color = "text-amber-600 dark:text-amber-400";
  } else if (["ts", "tsx"].includes(extension ?? "")) {
    Icon = FileCode2Icon;
    color = "text-blue-600 dark:text-blue-400";
  } else if (["py", "go", "rs", "java", "sh"].includes(extension ?? "")) {
    Icon = FileCode2Icon;
    color = "text-emerald-600 dark:text-emerald-400";
  } else if (["json", "yaml", "yml", "toml"].includes(extension ?? "")) {
    Icon = FileJsonIcon;
    color = "text-orange-600 dark:text-orange-400";
  } else if (["png", "jpg", "jpeg", "gif", "webp", "svg", "ico"].includes(extension ?? "")) {
    Icon = FileImageIcon;
    color = "text-violet-600 dark:text-violet-400";
  } else if (["md", "mdx", "txt", "docx", "pdf"].includes(extension ?? "")) {
    Icon = FileTextIcon;
    color =
      extension === "pdf" ? "text-red-600 dark:text-red-400" : "text-sky-600 dark:text-sky-400";
  }
  return <Icon aria-hidden="true" className={cn("size-3.5 shrink-0", color)} />;
}

export function FileTree({
  nodes,
  visibleCount,
  totalAdditions,
  totalDeletions,
  className,
  onSelectPath,
  renderFileRow,
  ...props
}: Omit<
  ComponentProps<"div">,
  "children" | "nodes" | "visibleCount" | "totalAdditions" | "totalDeletions"
> & {
  nodes: readonly FileTreeNode[];
  visibleCount: number;
  totalAdditions: number;
  totalDeletions: number;
  onSelectPath?: (path: string) => void;
  renderFileRow?: (node: FileTreeNode, row: ReactElement) => ReactNode;
}) {
  const files = nodes.filter((node) => node.kind === "file").length;

  return (
    <div
      data-slot="file-tree"
      className={cn(paper, "flex w-full max-w-sm flex-col gap-2 rounded-2xl p-3.5", className)}

      {...props}
    >
      <div className="flex items-baseline justify-between px-1">
        <span className="text-[13.5px] font-medium">{files} 个文件修改 · 累计增删</span>
        <span className={cn(mono, "tabular-nums")}>
          <span className="text-emerald-600 dark:text-emerald-400">+{totalAdditions}</span>{" "}
          <span className="text-red-600 dark:text-red-400">−{totalDeletions}</span>
        </span>
      </div>

      <div className="flex flex-col">
        {take(nodes, visibleCount).map((node) => {
          const row = (
            <button
              type="button"
              disabled={node.kind === "folder" || (!onSelectPath && !renderFileRow)}
              onClick={() => onSelectPath?.(node.path)}
              key={node.path}
              className="fade-in slide-in-from-left-1 animate-in fill-mode-both hover:bg-foreground/[0.03] flex items-center gap-2 rounded-lg px-1 py-1 text-start text-[13px] transition-colors duration-300"
              style={{ paddingInlineStart: `${0.25 + node.depth * 0.85}rem` }}
            >
              {node.kind === "folder" ? (
                <>
                  <ChevronDownIcon className="text-muted-foreground size-3 shrink-0" />
                  <FolderIcon
                    aria-hidden="true"
                    className="size-3.5 shrink-0 fill-amber-100 text-amber-600 dark:fill-amber-400/15 dark:text-amber-400"
                  />
                  <span className="text-foreground/60 min-w-0 flex-1 truncate">{node.name}</span>
                </>
              ) : (
                <>
                  <span className="ms-3 flex min-w-0 flex-1 items-center gap-2">
                    <FileTypeIcon path={node.path} />
                    <span className="text-foreground/85 truncate">{node.name}</span>
                  </span>
                  <span className={cn(mono, "shrink-0 tabular-nums")}>
                    {node.additions ? (
                      <span className="text-emerald-600 dark:text-emerald-400">
                        +{node.additions}
                      </span>
                    ) : null}{" "}
                    {node.deletions ? (
                      <span className="text-red-600 dark:text-red-400">−{node.deletions}</span>
                    ) : null}
                  </span>
                </>
              )}
            </button>
          );
          return (
            <Fragment key={node.path}>
              {node.kind === "file" && renderFileRow ? renderFileRow(node, row) : row}
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
