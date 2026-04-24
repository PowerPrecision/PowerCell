import * as React from "react"
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog"
import * as VisuallyHidden from "@radix-ui/react-visually-hidden"

import { cn } from "@/lib/utils"
import { buttonVariants } from "@/components/ui/button"

const AlertDialog = AlertDialogPrimitive.Root

const AlertDialogTrigger = AlertDialogPrimitive.Trigger

const AlertDialogPortal = AlertDialogPrimitive.Portal

const AlertDialogOverlay = React.forwardRef(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Overlay
    className={cn(
      "fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props}
    ref={ref} />
))
AlertDialogOverlay.displayName = AlertDialogPrimitive.Overlay.displayName

/**
 * AlertDialogContent component with built-in accessibility support.
 * 
 * @param {object} props
 * @param {string} [props.title] - Optional title for accessibility.
 * @param {string} [props.description] - Optional description for accessibility.
 */
const AlertDialogContent = React.forwardRef(({ 
  className, 
  children, 
  title,
  description,
  ...props 
}, ref) => {
  // Generate unique IDs for accessibility
  const descriptionId = React.useId()
  
  /**
   * Recursively check if children contain a specific component type.
   * This is needed because AlertDialogDescription might be nested inside AlertDialogHeader.
   */
  const hasComponentType = (children, targetType, targetDisplayName) => {
    return React.Children.toArray(children).some(child => {
      if (!React.isValidElement(child)) return false
      
      // Check direct match
      if (child.type === targetType || child.type?.displayName === targetDisplayName) {
        return true
      }
      
      // Check nested children (e.g., AlertDialogDescription inside AlertDialogHeader)
      if (child.props?.children) {
        return hasComponentType(child.props.children, targetType, targetDisplayName)
      }
      
      return false
    })
  }

  // Check if children already contain an AlertDialogTitle (recursively)
  const hasTitle = hasComponentType(children, AlertDialogTitle, AlertDialogTitle.displayName)

  // Check if children contain an AlertDialogDescription (recursively)
  const hasDescription = hasComponentType(children, AlertDialogDescription, AlertDialogDescription.displayName)

  // Determine if we need aria-describedby — always set it to avoid Radix console warning
  const ariaDescribedBy = descriptionId;

  return (
    <AlertDialogPortal>
      <AlertDialogOverlay />
      <AlertDialogPrimitive.Content
        ref={ref}
        aria-describedby={ariaDescribedBy}
        className={cn(
          "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 border bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=closed]:slide-out-to-top-[48%] data-[state=open]:slide-in-from-left-1/2 data-[state=open]:slide-in-from-top-[48%] sm:rounded-lg",
          className
        )}
        {...props}>
        {/* Render hidden title for accessibility if no visible title exists */}
        {!hasTitle && (
          <VisuallyHidden.Root>
            <AlertDialogPrimitive.Title>{title || "Alert"}</AlertDialogPrimitive.Title>
          </VisuallyHidden.Root>
        )}
        {/* Render hidden description for accessibility if no visible description exists */}
        {!hasDescription && !description && (
          <VisuallyHidden.Root>
            <AlertDialogPrimitive.Description id={descriptionId}>
              Ação irreversível
            </AlertDialogPrimitive.Description>
          </VisuallyHidden.Root>
        )}
        {/* Render provided description as hidden if specified */}
        {description && !hasDescription && (
          <VisuallyHidden.Root>
            <AlertDialogPrimitive.Description id={descriptionId}>{description}</AlertDialogPrimitive.Description>
          </VisuallyHidden.Root>
        )}
        {/* Clone children to pass id to AlertDialogDescription */}
        {React.Children.map(children, child => {
          if (React.isValidElement(child) && 
              (child.type === AlertDialogDescription || 
               child.type?.displayName === AlertDialogDescription.displayName)) {
            return React.cloneElement(child, { id: descriptionId })
          }
          return child
        })}
      </AlertDialogPrimitive.Content>
    </AlertDialogPortal>
  )
})
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName

const AlertDialogHeader = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col space-y-2 text-center sm:text-left", className)}
    {...props} />
)
AlertDialogHeader.displayName = "AlertDialogHeader"

const AlertDialogFooter = ({
  className,
  ...props
}) => (
  <div
    className={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:space-x-2", className)}
    {...props} />
)
AlertDialogFooter.displayName = "AlertDialogFooter"

const AlertDialogTitle = React.forwardRef(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Title ref={ref} className={cn("text-lg font-semibold", className)} {...props} />
))
AlertDialogTitle.displayName = AlertDialogPrimitive.Title.displayName

const AlertDialogDescription = React.forwardRef(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Description
    ref={ref}
    className={cn("text-sm text-muted-foreground", className)}
    {...props} />
))
AlertDialogDescription.displayName =
  AlertDialogPrimitive.Description.displayName

const AlertDialogAction = React.forwardRef(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Action ref={ref} className={cn(buttonVariants(), className)} {...props} />
))
AlertDialogAction.displayName = AlertDialogPrimitive.Action.displayName

const AlertDialogCancel = React.forwardRef(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Cancel
    ref={ref}
    className={cn(buttonVariants({ variant: "outline" }), "mt-2 sm:mt-0", className)}
    {...props} />
))
AlertDialogCancel.displayName = AlertDialogPrimitive.Cancel.displayName

export {
  AlertDialog,
  AlertDialogPortal,
  AlertDialogOverlay,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
}
