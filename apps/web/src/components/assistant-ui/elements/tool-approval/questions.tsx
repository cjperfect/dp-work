import type { ToolApprovalQuestion, ToolApprovalAnswer } from "@assistant-ui/react";
import { useState } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { pressable, questionAcceptsText } from "./model";

export function ToolFallbackApprovalQuestions({
  questions,
  dismissible,
  locked,
  onSend,
  onDismiss,
}: {
  questions: readonly ToolApprovalQuestion[];
  dismissible: boolean;
  locked: boolean;
  onSend: (answers: Record<string, ToolApprovalAnswer>) => void;
  onDismiss: () => void;
}) {
  const [selected, setSelected] = useState<ReadonlyMap<string, readonly string[]>>(() => new Map());
  const [typed, setTyped] = useState<ReadonlyMap<string, string>>(() => new Map());

  const toggle = (question: ToolApprovalQuestion, optionId: string) =>
    setSelected((current) => {
      const chosen = current.get(question.id) ?? [];
      const next = chosen.includes(optionId)
        ? chosen.filter((id) => id !== optionId)
        : question.multiple
          ? [...chosen, optionId]
          : [optionId];
      return new Map(current).set(question.id, next);
    });

  const answerOf = (question: ToolApprovalQuestion): ToolApprovalAnswer => {
    const optionIds = selected.get(question.id) ?? [];
    const draft = typed.get(question.id);
    const text = draft?.trim() ? draft : undefined;
    return {
      ...(optionIds.length > 0 && { optionIds }),
      ...(text !== undefined && { text }),
    };
  };

  const complete =
    questions.length > 0 &&
    questions.every((question) => {
      const answer = answerOf(question);
      return answer.optionIds !== undefined || answer.text !== undefined;
    });

  const send = () => {
    if (locked || !complete) return;
    onSend(Object.fromEntries(questions.map((question) => [question.id, answerOf(question)])));
  };

  return (
    <>
      {questions.map((question) => {
        const chosen = selected.get(question.id) ?? [];
        const described = question.options?.some((option) => option.description) ?? false;
        return (
          <div
            key={question.id}
            role="group"
            aria-label={question.prompt}
            data-slot="tool-fallback-approval-question"
            className="aui-tool-fallback-approval-question flex flex-col gap-2"
          >
            <p className="aui-tool-fallback-approval-question-prompt text-foreground whitespace-pre-line">
              {question.header ? (
                <span className="text-muted-foreground me-1.5 text-xs font-medium uppercase">
                  {question.header}
                </span>
              ) : null}
              {question.prompt}
            </p>
            {question.options && question.options.length > 0 ? (
              <div
                className={cn(
                  "flex gap-2",
                  described ? "flex-col items-stretch" : "flex-wrap items-center",
                )}
              >
                {question.options.map((option) => {
                  const pressed = chosen.includes(option.id);
                  return (
                    <Button
                      key={option.id}
                      size="sm"
                      variant={pressed ? "default" : "outline"}
                      className={cn(
                        pressable,
                        described &&
                          "h-auto flex-col items-start gap-0.5 py-2 text-start whitespace-normal",
                      )}
                      aria-pressed={pressed}
                      onClick={() => toggle(question, option.id)}
                      disabled={locked}
                    >
                      <span>{option.label}</span>
                      {option.description ? (
                        <span className="text-xs font-normal opacity-80">{option.description}</span>
                      ) : null}
                    </Button>
                  );
                })}
              </div>
            ) : null}
            {questionAcceptsText(question) ? (
              <Textarea
                value={typed.get(question.id) ?? ""}
                onChange={(event) =>
                  setTyped((current) => new Map(current).set(question.id, event.target.value))
                }
                disabled={locked}
                aria-label={question.prompt}
                placeholder={question.options?.length ? "或输入答案" : "输入你的答案"}
              />
            ) : null}
          </div>
        );
      })}
      <div className="flex items-center gap-2">
        <Button size="sm" className={pressable} onClick={send} disabled={locked || !complete}>
          发送
        </Button>
        {dismissible ? (
          <Button
            size="sm"
            variant="outline"
            className={pressable}
            onClick={onDismiss}
            disabled={locked}
          >
            忽略
          </Button>
        ) : null}
      </div>
    </>
  );
}
