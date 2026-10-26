import type { ReactNode } from "react";
import {
  Select,
  SelectTrigger,
  SelectContent,
  SelectItem,
  SelectValue,
} from "@/components/ui/select";

export function Row({
  label,
  description,
  children,
  top = false,
}: {
  label: string;
  description?: string;
  children: ReactNode;
  top?: boolean;
}) {
  return (
    <div
      className={`flex flex-col justify-between gap-3 py-4 sm:flex-row sm:gap-6 ${top ? "sm:items-start" : "sm:items-center"}`}
    >
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">{label}</div>
        {description && (
          <p className="text-muted-foreground mt-1 max-w-sm text-xs leading-relaxed">
            {description}
          </p>
        )}
      </div>
      <div className="w-full shrink-0 sm:w-[min(48%,340px)]">{children}</div>
    </div>
  );
}

export function Group({ children }: { children: ReactNode }) {
  return <div className="divide-border divide-y rounded-2xl border px-5">{children}</div>;
}

export function Choice({
  value,
  options,
  onChange,
  label,
  disabled,
}: {
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <Select
      value={value}
      onValueChange={(next) => {
        if (typeof next === "string") onChange(next);
      }}
      disabled={disabled}
    >
      <SelectTrigger className="w-full shadow-none" aria-label={label}>
        <SelectValue>{options.find((item) => item.value === value)?.label ?? value}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        {options.map((item) => (
          <SelectItem key={item.value} value={item.value}>
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
