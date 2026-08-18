import { describe, expect, it } from 'vitest'
import { shouldDismissModal } from './modalInteraction'

const overlayEvent = (target, currentTarget = target) => ({ target, currentTarget })

describe('modal overlay interaction', () => {
  it('dismisses on a direct click on the overlay', () => {
    const overlay = {}
    expect(shouldDismissModal(overlayEvent(overlay), false)).toBe(true)
  })

  it('does not dismiss after dragging from the dialog outside', () => {
    const overlay = {}
    expect(shouldDismissModal(overlayEvent(overlay), true)).toBe(false)
  })

  it('does not dismiss when the click target is inside the dialog', () => {
    const overlay = {}
    const dialog = {}
    expect(shouldDismissModal(overlayEvent(dialog, overlay), false)).toBe(false)
  })
})
