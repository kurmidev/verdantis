import { useEffect, useRef, type ReactNode } from 'react'

interface Props {
  open: boolean
  onClose: () => void
  label: string
  className?: string
  children: ReactNode
}

/** Native <dialog>: focus trap, Esc and focus return come from the platform. */
export function Dialog({ open, onClose, label, className = '', children }: Props) {
  const ref = useRef<HTMLDialogElement>(null)
  const openRef = useRef(open)
  useEffect(() => {
    openRef.current = open
    const el = ref.current
    if (!el) return
    if (open && !el.open) {
      if (typeof el.showModal === 'function') el.showModal()
      else el.setAttribute('open', '') // jsdom has no showModal
    } else if (!open && el.open) {
      if (typeof el.close === 'function') el.close()
      else el.removeAttribute('open')
    }
  }, [open])
  return (
    <dialog
      ref={ref}
      className={`dialog ${className}`}
      aria-label={label}
      onClose={() => openRef.current && onClose()}
      onClick={(e) => e.target === ref.current && onClose()}
    >
      {open && children}
    </dialog>
  )
}
