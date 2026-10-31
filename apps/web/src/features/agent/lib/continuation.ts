/** 仅识别独立的续接指令；包含新任务或补充要求的消息仍交给模型处理。 */
export function isContinuationRequest(text: string): boolean {
  const value = text
    .trim()
    .toLowerCase()
    .replace(/[\s。！!？?，,]/g, "");
  return (
    /^(?:(?:请你?|麻烦你?|好的)[，,]?)?(?:继续|接着)(?:执行|运行|处理|上次的任务|之前的任务)?吧?$/.test(
      value,
    ) || ["continue", "resume", "keepgoing"].includes(value)
  );
}
