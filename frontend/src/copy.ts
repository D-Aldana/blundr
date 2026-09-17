import type { Category, TimeControl } from './api'

export const CATEGORY_LABEL: Record<Category['name'], string> = {
  tactical: 'Tactics',
  endgame: 'Endgame technique',
  time_management: 'Time management',
  conversion: 'Conversion',
}

/** `step` is a machine key by design (PRD §14) so the wait can have a voice. */
export const STEP_COPY: Record<string, string> = {
  fetching_games: 'Pulling your last 20 games',
  evaluating_games: 'Stockfish is going through every move',
  classifying_weaknesses: 'Separating the blunders from the bad luck',
  generating_recommendations: 'Working out what you should drill',
  writing_summary: 'Writing the verdict',
}

export function failureCopy(code: string): string {
  switch (code) {
    case 'unreachable':
      return 'Cannot reach the analyzer. Check that the backend is running on port 8000.'
    case 'user_not_found':
      return 'No Chess.com account by that name. Check the spelling and try again.'
    case 'engine_unavailable':
      return 'The chess engine is not available, so no games could be analyzed.'
    case 'stockfish_timeout':
      return 'The engine ran out of time on these games. Try again.'
    case 'not_enough_games':
      return 'Those games disappeared between the check and the analysis. Try again.'
    default:
      return 'The analysis stopped partway through. Try again.'
  }
}

export const shortfallCopy = (
  count: number,
  tc: TimeControl,
  hasAlternatives: boolean,
) =>
  count === 0
    ? `No ${tc} games on record yet.` +
      (hasAlternatives ? ' You have enough in another time control:' : '')
    : `Only ${count} ${tc} game${count === 1 ? '' : 's'} on record — the report needs 20.` +
      (hasAlternatives ? ' You have enough in another time control:' : '')
