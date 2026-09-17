import { useEffect, useState } from 'react'
import { STEP_COPY } from '../copy'

const clock = (s: number) =>
  `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`

export function Analyzing({
  username,
  step,
  progress,
}: {
  username: string
  step: string
  progress: number
}) {
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const id = setInterval(() => setElapsed((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-5 py-16">
      <div className="flex items-baseline justify-between">
        <span className="label">Analyzing {username}</span>
        <span className="font-mono text-sm tabular-nums text-ink-soft">
          {clock(elapsed)}
        </span>
      </div>

      <p
        key={step}
        className="rise mt-4 font-display text-[clamp(1.75rem,6vw,2.75rem)] leading-tight font-semibold tracking-[-0.02em]"
      >
        {STEP_COPY[step] ?? 'Working through your games'}
      </p>

      <div className="mt-8 h-3 w-full border border-ink/25 bg-chalk">
        <div
          className="h-full bg-ink transition-[width] duration-700 ease-out"
          style={{ width: `${Math.round(progress * 100)}%` }}
        />
      </div>

      <p className="label mt-3 tabular-nums">{Math.round(progress * 100)}% complete</p>
    </main>
  )
}
