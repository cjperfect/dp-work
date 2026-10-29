import { PreviewCard } from "@base-ui/react/preview-card";
import { cn } from "@/lib/utils";

export const HoverCard = PreviewCard.Root;
export const HoverCardTrigger = PreviewCard.Trigger;

export function HoverCardContent({
  className,
  side = "top",
  align = "start",
  sideOffset = 8,
  ...props
}: PreviewCard.Popup.Props & Pick<PreviewCard.Positioner.Props, "side" | "align" | "sideOffset">) {
  return (
    <PreviewCard.Portal>
      <PreviewCard.Positioner
        side={side}
        align={align}
        sideOffset={sideOffset}
        className="z-50 isolate max-w-[calc(100vw-2rem)]"
      >
        <PreviewCard.Popup
          data-slot="hover-card-content"
          className={cn(
            "max-h-[min(70vh,var(--available-height))] w-[min(48rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border bg-popover p-3 text-popover-foreground shadow-lg outline-none",
            className,
          )}
          {...props}
        />
      </PreviewCard.Positioner>
    </PreviewCard.Portal>
  );
}
