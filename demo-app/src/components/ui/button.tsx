import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../../lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap text-xs font-sans uppercase tracking-widest transition-all duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-950 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 sharp-corners",
  {
    variants: {
      variant: {
        default:
          "bg-foreground text-background border border-transparent hover:bg-white hover:text-foreground hover:border-foreground",
        outline:
          "border border-foreground bg-transparent text-foreground hover:bg-foreground hover:text-background",
        ghost: "hover:bg-muted hover:text-foreground",
        link: "text-foreground underline-offset-4 decoration-2 decoration-accent hover:underline",
      },
      size: {
        default: "min-h-[44px] min-w-[44px] px-6 py-2",
        sm: "min-h-[36px] min-w-[36px] px-4 py-1",
        lg: "min-h-[56px] min-w-[56px] px-8 py-3",
        icon: "h-11 w-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => {
    return (
      <button
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
