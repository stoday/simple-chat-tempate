export const shouldDismissModal = (event, pointerStartedInside) => (
  event.target === event.currentTarget && !pointerStartedInside
)
