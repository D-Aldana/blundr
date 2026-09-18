import { useState } from 'react'
import { TIME_CONTROLS, type TimeControl } from '../api'
import { shortfallCopy } from '../copy'

export type Shortfall = {
  game_count: number
  time_control: TimeControl
  alternatives: { time_control: TimeControl; game_count: number }[]
}

type Props = {
  busy: boolean
  error: string | null
  shortfall: Shortfall | null
  onSubmit: (username: string, timeControl: TimeControl) => void
}

export function Scoresheet({ busy, error, shortfall, onSubmit }: Props) {
  const [username, setUsername] = useState('')
  const [timeControl, setTimeControl] = useState<TimeControl>('blitz')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (username.trim() && !busy) onSubmit(username.trim(), timeControl)
  }

  return (
    <main className="mx-auto flex min-h-dvh max-w-2xl flex-col justify-center px-5 py-16">
      <header className="rise">
        <span className="label">Chess.com weakness report</span>
        <h1 className="mt-2 font-display text-[clamp(2.75rem,10vw,4.5rem)] leading-[0.88] font-extrabold tracking-[-0.03em]">
          Blund<span className="text-blunder">r</span>
        </h1>
        <p className="mt-5 max-w-md text-lg text-ink-soft italic">
          Twenty games, read move by move. One uncomfortable truth about your
          chess, and what to do about it.
        </p>
      </header>

      <form
        onSubmit={submit}
        className="rise mt-10 border border-ink/25 bg-chalk p-6 shadow-[6px_6px_0_rgba(16,33,74,0.08)] sm:p-8"
        style={{ animationDelay: '90ms' }}
      >
        <label htmlFor="username" className="label block">
          Player
        </label>
        <input
          id="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="chess.com username"
          autoComplete="off"
          autoCapitalize="off"
          spellCheck={false}
          className="mt-2 w-full border-b-2 border-ink/25 bg-transparent pb-2 font-mono text-2xl
                     placeholder:text-ink/25 focus:border-ink focus:outline-none"
        />

        <fieldset className="mt-8">
          <legend className="label">Event</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {TIME_CONTROLS.map((tc) => (
              <button
                key={tc}
                type="button"
                onClick={() => setTimeControl(tc)}
                aria-pressed={timeControl === tc}
                className={`border px-5 py-2 font-mono text-sm tracking-wide transition-colors ${
                  timeControl === tc
                    ? 'border-ink bg-ink text-paper'
                    : 'border-ink/25 text-ink-soft hover:border-ink hover:text-ink'
                }`}
              >
                {tc}
              </button>
            ))}
          </div>
        </fieldset>

        <button
          type="submit"
          disabled={!username.trim() || busy}
          className="mt-9 w-full bg-ink px-6 py-4 font-display text-lg font-semibold text-paper
                     transition-opacity hover:opacity-90 disabled:opacity-30"
        >
          {busy ? 'Checking…' : 'Analyze my last 20 games'}
        </button>

        {shortfall && (
          <div className="mt-6 border-l-2 border-blunder pl-4">
            <p className="text-ink-soft">
              {shortfallCopy(
                shortfall.game_count,
                shortfall.time_control,
                shortfall.alternatives.length > 0,
              )}
            </p>
            {shortfall.alternatives.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {shortfall.alternatives.map((alt) => (
                  <button
                    key={alt.time_control}
                    type="button"
                    onClick={() => {
                      setTimeControl(alt.time_control)
                      onSubmit(username.trim(), alt.time_control)
                    }}
                    className="border border-ink px-4 py-2 font-mono text-sm hover:bg-ink hover:text-paper"
                  >
                    {alt.time_control} · {alt.game_count} games
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {error && (
          <p className="mt-6 border-l-2 border-blunder pl-4 text-ink-soft">{error}</p>
        )}
      </form>

      <p className="label mt-6 text-center">
        No signup · free · about 30 seconds
      </p>
    </main>
  )
}
