import { useState } from 'react'
import type { Category, Report as ReportData } from '../api'
import {
  CATEGORY_HELP,
  CATEGORY_LABEL,
  CONFIDENCE_HELP,
  SCORE_HELP,
} from '../copy'
import { Tooltip } from './Tooltip'

/** Mirrors the backend's ranking (recommend.rank_categories): worst first. */
const rank = (categories: Category[]) =>
  categories
    .filter((c) => c.confidence !== 'insufficient' && c.score > 0)
    .sort((a, b) => b.score - a.score || b.instances - a.instances)

const ConfidenceTip = () => (
  <span className="ml-1.5">
    <Tooltip label="What confidence means" text={CONFIDENCE_HELP} align="right" />
  </span>
)

function EvalBar({
  category,
  worst,
  delay,
}: {
  category: Category
  worst: boolean
  delay: number
}) {
  // Too few opportunities to score at all — show the track empty rather than
  // drawing a number the sample cannot support.
  const unscored = category.confidence === 'insufficient'

  return (
    <li className="grid grid-cols-[1fr_auto] items-baseline gap-x-4 gap-y-2 py-4 sm:grid-cols-[13rem_1fr_auto]">
      <span
        className={`flex items-center gap-1.5 font-display font-semibold ${unscored ? 'text-ink-soft' : ''}`}
      >
        {CATEGORY_LABEL[category.name]}
        <Tooltip
          label={`What ${CATEGORY_LABEL[category.name]} measures`}
          text={CATEGORY_HELP[category.name]}
        />
      </span>

      <div className="col-span-2 order-last h-2.5 border border-ink/20 bg-paper sm:order-none sm:col-span-1">
        {!unscored && (
          <div
            className={`sweep h-full ${worst ? 'bg-blunder' : 'bg-ink'}`}
            style={{ width: `${category.score * 100}%`, animationDelay: `${delay}ms` }}
          />
        )}
      </div>

      <span className="text-right font-mono text-sm tabular-nums text-ink-soft">
        {unscored ? (
          <>
            too few to judge
            <ConfidenceTip />
          </>
        ) : (
          <>
            {category.score.toFixed(2)}
            <span className="ml-2 opacity-60">{category.instances}×</span>
            {category.confidence === 'low' && (
              <>
                <span className="ml-2 opacity-60">low confidence</span>
                <ConfidenceTip />
              </>
            )}
          </>
        )}
      </span>
    </li>
  )
}

export function Report({
  report,
  onRestart,
}: {
  report: ReportData
  onRestart: () => void
}) {
  const [copied, setCopied] = useState(false)
  const ranked = rank(report.categories)
  const worst = ranked[0]

  const copy = async () => {
    await navigator.clipboard.writeText(
      `${report.headline}\n\n${report.summary}\n\n— Blundr, ${report.games_analyzed} ${report.time_control} games as ${report.username}`,
    )
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Browsers name the saved PDF after the document title.
  const print = () => {
    const title = document.title
    document.title = `blundr-${report.username}-${report.time_control}`
    window.addEventListener('afterprint', () => (document.title = title), {
      once: true,
    })
    window.print()
  }

  return (
    <main className="mx-auto max-w-2xl px-5 py-16">
      <div className="flex items-baseline justify-between">
        <span className="label">{report.username}</span>
        <span className="label">
          {report.games_analyzed} {report.time_control} games
        </span>
      </div>

      {/* The headline set as an annotated move — ?? is chess for "blunder". */}
      <header className="rise mt-6 flex gap-5">
        <span
          aria-hidden
          className={`font-display text-6xl leading-[0.7] font-extrabold ${
            worst ? 'text-blunder' : 'text-ink-soft'
          }`}
        >
          {worst ? '??' : '='}
        </span>
        <h1 className="font-display text-[clamp(1.6rem,5.5vw,2.4rem)] leading-[1.05] font-extrabold tracking-[-0.02em]">
          {report.headline}
        </h1>
      </header>

      <section className="rise mt-14" style={{ animationDelay: '120ms' }}>
        <h2 className="label flex items-center gap-2 border-b border-ink/25 pb-2">
          Four fundamentals
          <Tooltip label="How these scores are calculated" text={SCORE_HELP} />
        </h2>
        <ul className="divide-y divide-ink/10">
          {report.categories.map((c, i) => (
            <EvalBar
              key={c.name}
              category={c}
              worst={c.name === worst?.name}
              delay={200 + i * 110}
            />
          ))}
        </ul>
      </section>

      <section className="rise mt-14" style={{ animationDelay: '200ms' }}>
        <h2 className="label border-b border-ink/25 pb-2">What to drill</h2>
        {report.recommendations.map((rec) => (
          <article key={rec.category} className="mt-6">
            <h3 className="font-display font-semibold">
              {CATEGORY_LABEL[rec.category]}
            </h3>
            <p className="mt-2 text-lg leading-relaxed">{rec.text}</p>
            <p className="mt-3 border-l-2 border-ink/20 pl-4 font-mono text-[0.8rem] leading-relaxed text-ink-soft">
              {rec.evidence}
            </p>
          </article>
        ))}
      </section>

      <section className="rise mt-14" style={{ animationDelay: '280ms' }}>
        <h2 className="label border-b border-ink/25 pb-2">The verdict</h2>
        <p className="mt-6 text-xl leading-relaxed">{report.summary}</p>
        {report.summary_source === 'fallback' && (
          <p className="label mt-4">Written from your numbers, not by the model</p>
        )}
      </section>

      <footer className="no-print mt-14 flex flex-wrap gap-3 border-t border-ink/25 pt-6">
        <button
          onClick={copy}
          className="border border-ink px-5 py-2.5 font-mono text-sm hover:bg-ink hover:text-paper"
        >
          {copied ? 'Copied' : 'Copy result'}
        </button>
        <button
          onClick={print}
          className="border border-ink px-5 py-2.5 font-mono text-sm hover:bg-ink hover:text-paper"
        >
          Save as PDF
        </button>
        <button
          onClick={onRestart}
          className="px-5 py-2.5 font-mono text-sm text-ink-soft hover:text-ink"
        >
          Analyze another player
        </button>
      </footer>
    </main>
  )
}
