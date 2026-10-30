import type {
  ToolApprovalOption,
  ToolApprovalQuestion,
  ToolApprovalAnswer,
  ToolCallMessagePart,
} from "@assistant-ui/react";
export const pressable = "active:scale-[0.98]";

export const APPROVED_RESULT = "用户已批准";
export const DENIED_RESULT = "用户已拒绝工具执行";

export const APPROVAL_OPTION_DEFAULT_LABELS: Record<string, string> = {
  "allow-once": "允许",
  "allow-always": "始终允许",
  "reject-once": "拒绝",
  "reject-always": "始终拒绝",
};

export const isKnownKind = (kind: string) => Object.hasOwn(APPROVAL_OPTION_DEFAULT_LABELS, kind);

export const isAllowKind = (kind: string) => kind === "allow-once" || kind === "allow-always";

export const approvalOptionLabel = (option: ToolApprovalOption) =>
  option.label ??
  (isKnownKind(option.kind) ? APPROVAL_OPTION_DEFAULT_LABELS[option.kind] : undefined) ??
  option.id;

/**
 * A request that declares how it wants to be presented is asking a question,
 * not gating an action, so a refusal is not one of the answers it accepts
 * unless the request declares itself dismissible.
 */
export const isQuestion = (approval: ToolCallMessagePart["approval"]) =>
  approval?.display === "select" ||
  approval?.display === "text" ||
  approval?.display === "questions";

export const questionAcceptsText = (question: ToolApprovalQuestion) =>
  !question.options?.length || question.allowFreeform === true;

export const answerLabels = (
  question: ToolApprovalQuestion,
  answer: ToolApprovalAnswer | undefined,
) => [
  ...(answer?.optionIds ?? []).map(
    (id) => question.options?.find((option) => option.id === id)?.label ?? id,
  ),
  ...(answer?.text?.trim() ? [answer.text] : []),
];

export const isSettled = (approval: ToolCallMessagePart["approval"]) =>
  approval != null && (approval.approved !== undefined || approval.resolution !== undefined);

export type ApprovalReceipt = {
  outcome: "allowed" | "refused" | "closed";
  label: string;
  option?: string | undefined;
};

/**
 * A settled request reads as a past-tense record of what happened to it, so
 * scrolling back never shows a live control for a decision already made.
 */
export const approvalReceipt = (
  approval: NonNullable<ToolCallMessagePart["approval"]>,
): ApprovalReceipt => {
  if (approval.resolution !== undefined)
    return {
      outcome: "closed",
      label: approval.resolution === "cancelled" ? "在决策前取消" : "在决策前过期",
    };

  const chosen =
    approval.optionId === undefined
      ? undefined
      : approval.options?.find((option) => option.id === approval.optionId);
  const option =
    chosen !== undefined
      ? approvalOptionLabel(chosen)
      : approval.optionId === undefined
        ? undefined
        : approval.optionId;
  const answered = isQuestion(approval) || (chosen !== undefined && !isKnownKind(chosen.kind));
  const automatic = approval.isAutomatic ? "（自动）" : "";

  if (approval.approved)
    return {
      outcome: "allowed",
      label: `${answered ? "已回答" : "已允许"}${automatic}`,
      option,
    };
  return {
    outcome: "refused",
    label: `${answered ? "已忽略" : "已拒绝"}${automatic}`,
    option,
  };
};
