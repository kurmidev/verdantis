import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

type Kind = 'info' | 'error'
const ToastCtx = createContext<(msg: string, kind?: Kind) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

const SHOW_MS = 6000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<{ id: number; msg: string; kind: Kind }[]>([])
  const push = useCallback((msg: string, kind: Kind = 'info') => {
    const id = Date.now() + Math.random()
    setItems((xs) => [...xs, { id, msg, kind }])
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), SHOW_MS)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts">
        <div role="status" aria-live="polite">
          {items.filter((i) => i.kind === 'info').map((i) => <p className="toast" key={i.id}>{i.msg}</p>)}
        </div>
        <div role="alert">
          {items.filter((i) => i.kind === 'error').map((i) => <p className="toast toast-error" key={i.id}>{i.msg}</p>)}
        </div>
      </div>
    </ToastCtx.Provider>
  )
}
