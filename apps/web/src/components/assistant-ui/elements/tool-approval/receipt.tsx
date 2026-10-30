import type { ToolCallMessagePart } from "@assistant-ui/react";
import { useLayoutEffect } from "react";
import { CheckIcon, XCircleIcon, CircleMinusIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { approvalReceipt, answerLabels, type ApprovalReceipt } from "./model";

const receiptIcons = {
  allowed: CheckIcon,
  refused: XCircleIcon,
  closed: CircleMinusIcon,
} satisfies Record<ApprovalReceipt["outcome"], React.ElementType>;

export function ToolFallbackApprovalReceipt({
  approval,
  className,
  focusReceiptRef,
  receiptRef,
  ...props
}: React.ComponentPropsWithoutRef<"div"> & {
  approval: NonNullable<ToolCallMessagePart["approval"]>;
  focusReceiptRef: React.MutableRefObject<string | null | undefined>;
  receiptRef: React.MutableRefObject<HTMLDivElement | null>;
}) {
  useLayoutEffect(() => {
    const shouldFocus = focusReceiptRef.current === approval.id;
    focusReceiptRef.current = null;
    if (shouldFocus) receiptRef.current?.focus({ preventScroll: true });
  }, [approval.id, focusReceiptRef, receiptRef]);

  const receipt = approvalReceipt(approval);
  const Icon = receiptIcons[receipt.outcome];
  const notes = [
    ...new Set(
      [approval.text, approval.reason].filter(
        (value): value is string => typeof value === "string" && value !== "",
      ),
    ),
  ];

  return (
    <div
      ref={receiptRef}
      data-slot="tool-fallback-approval-receipt"
      data-outcome={receipt.outcome}
      tabIndex={-1}
      className={cn("aui-tool-fallback-approval-receipt flex flex-col gap-1.5 pt-1", className)}
      {...props}
    >
      {approval.prompt ? (
        <p className="aui-tool-fallback-approval-prompt text-muted-foreground whitespace-pre-line">
          {approval.prompt}
        </p>
      ) : null}
      <p className="aui-tool-fallback-approval-receipt-label flex items-center gap-1.5">
        <Icon aria-hidden className="text-muted-foreground size-3.5 shrink-0" />
        <span className="font-medium">{receipt.label}</span>
        {receipt.option !== undefined ? (
          <span className="text-muted-foreground">· {receipt.option}</span>
        ) : null}
      </p>
      {approval.answers &&
        approval.questions?.map((question) => {
          const labels = answerLabels(
            question,
            approval.answers && Object.hasOwn(approval.answers, question.id)
              ? approval.answers[question.id]
              : undefined,
          );
          if (labels.length === 0) return null;
          return (
            <p
              key={question.id}
              className="aui-tool-fallback-approval-receipt-answer whitespace-pre-line"
            >
              <span className="text-muted-foreground">{question.header ?? question.prompt}</span> ·{" "}
              {labels.join(", ")}
            </p>
          );
        })}
      {notes.map((text) => (
        <p
          key={text}
          className="aui-tool-fallback-approval-receipt-note text-muted-foreground whitespace-pre-line"
        >
          {text}
        </p>
      ))}
    </div>
  );
}
