import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import * as VisuallyHidden from "@radix-ui/react-visually-hidden"
import { X } from "lucide-react"

import { cn } from "@/lib/utils"

const Dialog = DialogPrimitive.Root

const DialogTrigger = DialogPrimitive.Trigger

const DialogPortal = DialogPrimitive.Portal

const DialogClose = DialogPrimitive.Close

const DialogOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80  data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props} />
))
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName

/**
 * DialogContent component with built-in accessibility support.
 * 
 * @param {object} props
 * @param {string} [props.title] - Optional title for accessibility. If provided, will be rendered as hidden title.
 * @param {string} [props.description] - Optional description for accessibility.
 */
const DialogContent = React.forwardRef(({ 
  className, 
  children, 
  title,
  description,
  ...props 
}, ref) => {
  // Check if children already contain a DialogTitle
  const hasTitle = React.Children.toArray(children).some(
    child => React.isValidElement(child) && 
    (child.type === DialogTitle || 
     child.type?.displayName === DialogTitle.displayName ||
     child.type === DialogHeader)
  )

  // Check if children contain a DialogDescription (including nested in DialogHeader)
  const hasDescription = React.Children.toArray(children).some(
    child => {
      if (!React.isValidElement(child)) return false;
      if (child.type === DialogDescription || child.type?.displayName === DialogDescription.displayName) return true;
      // Also look inside DialogHeader
      if (child.type === DialogHeader || child.type?.displayName === DialogHeader.displayName) {
        return React.Children.toArray(child.props.children).some(
          gc => React.isValidElement(gc) && (gc.type === DialogDescription || gc.type?.displayName === DialogDescription.displayName)
        );
      }
      return false;
    }
  )

  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        ref={ref}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 grid w-[calc(100%-2rem)] sm:w-full max-w-lg max-h-[90vh] overflow-y-auto translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-4 sm:p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
          className
        )}
        {...props}
        aria-describedby={undefined}>
        {/* Render hidden title for accessibility if no visible title exists */}
        {!hasTitle && (
          <VisuallyHidden.Root>
            <DialogPrimitive.Title>{title || "Dialog"}</DialogPrimitive.Title>
          </VisuallyHidden.Root>
        )}
        {/* Always render a hidden DialogPrimitive.Description so Radix finds it and suppresses the warning */}
        {!hasDescription && (
          <VisuallyHidden.Root>
            <DialogPrimitive.Description>{description || ""}</DialogPrimitive.Description>
          </VisuallyHidden.Root>
        )}
        {children}
        <DialogPrimitive.Close
          className="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:pointer-events-none data-[state=open]:bg-accent data-[state=open]:text-muted-foreground">
          <X className="h-4 w-4" />
          <span className="sr-only">Close</span>
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPortal>
  )
})
DialogContent.displayName = DialogPrimitive.Content.displayName

const DialogHeader = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)}
    {...props} />
)
DialogHeader.displayName = "DialogHeader"

const DialogFooter = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2", className)}
    {...props} />
)
DialogFooter.displayName = "DialogFooter"

const DialogTitle = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props} />
))
DialogTitle.displayName = DialogPrimitive.Title.displayName

const DialogDescription = React.forwardRef(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props} />
))
DialogDescription.displayName = DialogPrimitive.Description.displayName

export {
  Dialog,
  DialogPortal,
  DialogOverlay,
  DialogTrigger,
  DialogClose,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
}
