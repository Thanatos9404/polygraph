import * as React from "react";
import * as SwitchPrimitives from "@radix-ui/react-switch";
import { cn } from "@/lib/utils";

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    ref={ref}
    className={cn(
      "peer inline-flex h-10 w-[76px] shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent shadow-soft transition-colors duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:bg-signal data-[state=unchecked]:bg-foreground/85",
      className,
    )}
    {...props}
  >
    <SwitchPrimitives.Thumb className="pointer-events-none block h-8 w-8 rounded-full bg-background shadow-lift ring-0 transition-transform duration-500 [transition-timing-function:cubic-bezier(.3,1.6,.5,1)] data-[state=checked]:translate-x-[38px] data-[state=unchecked]:translate-x-0.5" />
  </SwitchPrimitives.Root>
));
Switch.displayName = SwitchPrimitives.Root.displayName;

export { Switch };
