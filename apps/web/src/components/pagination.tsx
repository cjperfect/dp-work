import { cn } from "cn";
import {
  Pagination as PaginationRoot,
  PaginationContent,
  PaginationItem,
  PaginationPrevious,
  PaginationNext,
} from "@/components/ui/pagination";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const DEFAULT_PAGE_SIZES = [12, 24, 48];

export type PaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  pageSizeOptions?: readonly number[];
  disabled?: boolean;
  className?: string;
};

/** 展示每页条数、页码和翻页操作。 */
export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = DEFAULT_PAGE_SIZES,
  disabled = false,
  className,
}: PaginationProps) {
  const totalPages = Math.ceil(total / pageSize);
  const sizes = [...new Set([...pageSizeOptions, pageSize])].sort((a, b) => a - b);

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground",
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span>每页</span>
        <Select
          value={String(pageSize)}
          disabled={disabled}
          onValueChange={(value) => {
            if (value === null || Number(value) === pageSize) return;
            onPageSizeChange(Number(value));
            onPageChange(1);
          }}
        >
          <SelectTrigger size="sm" aria-label="每页条数">
            <SelectValue>{pageSize} 条</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {sizes.map((size) => (
              <SelectItem key={size} value={String(size)}>
                {size} 条
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <PaginationRoot className="mx-0 w-auto">
        <PaginationContent className="gap-3">
          <PaginationItem>
            <PaginationPrevious
              href="#"
              text=""
              title="上一页"
              className="border border-input"
              disabled={disabled || totalPages === 0 || page <= 1}
              onClick={(event) => {
                event.preventDefault();
                if (!disabled && totalPages > 0 && page > 1)
                  onPageChange(Math.min(page - 1, totalPages));
              }}
            />
          </PaginationItem>
          <PaginationItem>
            <span aria-live="polite">
              第 {totalPages ? page : 0} 页 / 共 {totalPages} 页
            </span>
          </PaginationItem>
          <PaginationItem>
            <PaginationNext
              href="#"
              text=""
              title="下一页"
              className="border border-input"
              disabled={disabled || page >= totalPages}
              onClick={(event) => {
                event.preventDefault();
                if (!disabled && page < totalPages) onPageChange(page + 1);
              }}
            />
          </PaginationItem>
        </PaginationContent>
      </PaginationRoot>
    </div>
  );
}
