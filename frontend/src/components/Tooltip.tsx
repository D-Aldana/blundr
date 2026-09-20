import { useEffect, useId, useRef, useState } from 'react'

type Props = {
  /** Names what is being explained, for screen readers: "What tactics means". */
  label: string
  text: string
  align?: 'left' | 'right'
}

/** Hover and focus open it; click toggles, so it works on touch too. */
export function Tooltip({ label, text, align = 'left' }: Props) {
  const [open, setOpen] = useState(false)
  const id = useId()
  const wrap = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    const onPointer = (e: PointerEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('pointerdown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('pointerdown', onPointer)
    }
  }, [open])

  return (
    <span
      ref={wrap}
      className="no-print relative inline-block align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        aria-describedby={open ? id : undefined}
        onClick={() => setOpen((o) => !o)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        className="grid h-[1.15em] w-[1.15em] place-items-center rounded-full border border-ink/35 font-mono text-[0.6em] leading-none text-ink-soft hover:border-ink hover:text-ink"
      >
        ?
      </button>

      {open && (
        <span
          role="tooltip"
          id={id}
          className={`absolute top-[calc(100%+0.5rem)] z-10 block w-64 border border-ink/25 bg-chalk p-3 text-left font-body text-sm leading-relaxed font-normal tracking-normal text-ink normal-case shadow-[4px_4px_0_rgba(16,33,74,0.08)] ${
            align === 'right' ? 'right-0' : 'left-0'
          }`}
        >
          {text}
        </span>
      )}
    </span>
  )
}
