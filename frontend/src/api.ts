const BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export const TIME_CONTROLS = ['bullet', 'blitz', 'rapid'] as const
export type TimeControl = (typeof TIME_CONTROLS)[number]

export type Eligibility =
  | { eligible: true; game_count: number }
  | {
      eligible: false
      game_count: number
      alternatives: { time_control: TimeControl; game_count: number }[]
    }

export type Category = {
  name: 'tactical' | 'endgame' | 'time_management' | 'conversion'
  score: number
  confidence: 'ok' | 'low' | 'insufficient'
  instances: number
}

export type Report = {
  username: string
  headline: string
  categories: Category[]
  recommendations: { category: Category['name']; text: string; evidence: string }[]
  summary: string
  summary_source: 'llm' | 'fallback'
  games_analyzed: number
  time_control: TimeControl
}

export type Job =
  | { status: 'running'; step: string; progress: number; queue_position?: number }
  | { status: 'done'; report: Report }
  | { status: 'failed'; error: string }

/** Backend errors arrive as FastAPI's {detail: {error: code}}; carry the code up. */
export class ApiError extends Error {
  code: string

  constructor(code: string) {
    super(code)
    this.code = code
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let resp: Response
  try {
    resp = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError('unreachable')
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    throw new ApiError(body?.detail?.error ?? 'request_failed')
  }
  return resp.json()
}

export const checkEligibility = (username: string, time_control: TimeControl) =>
  post<Eligibility>('/eligibility', { username, time_control })

export const startAnalysis = (username: string, time_control: TimeControl) =>
  post<{ job_id: string }>('/analyze', { username, time_control })

export async function getJob(jobId: string): Promise<Job> {
  const resp = await fetch(`${BASE}/analyze/${jobId}`)
  if (!resp.ok) throw new ApiError('job_not_found')
  return resp.json()
}
