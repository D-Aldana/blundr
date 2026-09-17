import { useEffect, useRef, useState } from 'react'
import {
  ApiError,
  checkEligibility,
  getJob,
  startAnalysis,
  type Report as ReportData,
  type TimeControl,
} from './api'
import { failureCopy } from './copy'
import { Analyzing } from './components/Analyzing'
import { Report } from './components/Report'
import { Scoresheet, type Shortfall } from './components/Scoresheet'

const POLL_MS = 1200

type Phase =
  | { name: 'form' }
  | { name: 'running'; username: string; step: string; progress: number }
  | { name: 'report'; report: ReportData }

export default function App() {
  const [phase, setPhase] = useState<Phase>({ name: 'form' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [shortfall, setShortfall] = useState<Shortfall | null>(null)
  const jobId = useRef<string | null>(null)

  const submit = async (username: string, timeControl: TimeControl) => {
    setBusy(true)
    setError(null)
    setShortfall(null)
    try {
      const eligibility = await checkEligibility(username, timeControl)
      if (!eligibility.eligible) {
        setShortfall({
          game_count: eligibility.game_count,
          time_control: timeControl,
          alternatives: eligibility.alternatives,
        })
        return
      }
      const { job_id } = await startAnalysis(username, timeControl)
      jobId.current = job_id
      setPhase({ name: 'running', username, step: 'fetching_games', progress: 0 })
    } catch (err) {
      setError(failureCopy(err instanceof ApiError ? err.code : 'request_failed'))
    } finally {
      setBusy(false)
    }
  }

  // Poll only while a job is in flight; any terminal state tears the timer down.
  useEffect(() => {
    if (phase.name !== 'running' || !jobId.current) return
    let active = true

    const id = setInterval(async () => {
      try {
        const job = await getJob(jobId.current!)
        if (!active) return
        if (job.status === 'done') {
          jobId.current = null
          setPhase({ name: 'report', report: job.report })
        } else if (job.status === 'failed') {
          jobId.current = null
          setError(failureCopy(job.error))
          setPhase({ name: 'form' })
        } else {
          setPhase((p) =>
            p.name === 'running'
              ? { ...p, step: job.step, progress: job.progress }
              : p,
          )
        }
      } catch {
        if (!active) return
        jobId.current = null
        setError(failureCopy('unreachable'))
        setPhase({ name: 'form' })
      }
    }, POLL_MS)

    return () => {
      active = false
      clearInterval(id)
    }
  }, [phase.name])

  if (phase.name === 'running') {
    return (
      <Analyzing
        username={phase.username}
        step={phase.step}
        progress={phase.progress}
      />
    )
  }

  if (phase.name === 'report') {
    return (
      <Report report={phase.report} onRestart={() => setPhase({ name: 'form' })} />
    )
  }

  return (
    <Scoresheet
      busy={busy}
      error={error}
      shortfall={shortfall}
      onSubmit={submit}
    />
  )
}
