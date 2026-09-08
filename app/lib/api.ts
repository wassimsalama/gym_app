/**
 * The API surface, expressed as typed functions.
 *
 * Reads go straight out over HTTP. Writes go through the offline queue (§8):
 * durably stored, applied optimistically, flushed when the network allows.
 */

import { api, ApiError, request } from '@/lib/http';
import type { IsoDate } from '@/lib/dates';
import { enqueue } from '@/lib/sync';
import type { Unit } from '@/lib/units';

export { ApiError, API_URL } from '@/lib/http';

// ---------------------------------------------------------------------------
// Response types mirroring api/app/schemas.
// ---------------------------------------------------------------------------

export type Health = { status: string };

export type AuthHealth = {
  status: string;
  user_id: string;
  unit: 'kg' | 'lb';
};

export type Split = 'push' | 'pull' | 'legs' | 'upper' | 'lower' | 'full' | 'other';

/** Weights are kg everywhere on the wire (spec §5); convert only in lib/units.ts. */
export type DailyLog = {
  log_date: IsoDate;
  weight_kg: number | null;
  /** null means the day was never logged, which is not the same as 0. */
  steps: number | null;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  trained: boolean | null;
  split: string | null;
};

/** Only the keys present are written; omitted keys are left untouched (§6). */
export type DailyLogPatch = Partial<Omit<DailyLog, 'log_date'>>;

export type Goal = {
  id: number;
  start_weight_kg: number;
  goal_weight_kg: number;
  start_date: IsoDate;
  target_date: IsoDate | null;
  status: 'active' | 'achieved' | 'abandoned';
};

export type WeightSeriesPoint = {
  date: IsoDate;
  raw_kg: number;
  smoothed_kg: number;
};

export type Dashboard = {
  streaks: { logged_14: number; trained_14: number };
  weight: {
    current_smoothed_kg: number | null;
    delta_since_start_kg: number | null;
    series: WeightSeriesPoint[];
  };
  goal: {
    progress_pct: number;
    projected_date: IsoDate | null;
    on_track: boolean | null;
    start_weight_kg: number;
    goal_weight_kg: number;
  } | null;
  /** `average` is null when nothing in the window was logged. Unlogged days are
   *  skipped, never counted as zero. */
  steps: {
    today: number | null;
    average: number | null;
    days_logged: number;
    reliable: boolean;
  };
  tdee: { estimate_kcal: number | null; days_of_data: number; reliable: boolean };
  volume: { muscle_group: string; sets_this_week: number; weekly_target: number }[];
  prs_recent: {
    exercise_id: number;
    exercise_name: string;
    e1rm: number;
    previous_e1rm: number;
    achieved_on: IsoDate;
  }[];
  suggestions: {
    id: string;
    kind: 'plateau' | 'tdee_update' | 'volume_gap' | 'goal_projection' | 'logging_nudge';
    message: string;
    evidence: Record<string, unknown>;
  }[];
  recap: {
    week_start: IsoDate;
    week_end: IsoDate;
    sessions: number;
    total_sets: number;
    total_volume_kg: number;
    weight_delta_kg: number | null;
    days_trained: number;
    days_logged: number;
    best_lift: {
      exercise_id: number;
      exercise_name: string;
      e1rm: number;
      previous_best: number | null;
      was_a_record: boolean;
    } | null;
  } | null;
};

export const health = () => request<Health>('/health', { anonymous: true });
export const healthAuth = () => api.get<AuthHealth>('/health-auth');

/**
 * Change the display unit.
 *
 * Deliberately not routed through the offline queue. The queue exists so a
 * logged set or weight survives a dead connection; a preference is worth
 * nothing if it syncs an hour later, and queueing it would let two devices
 * replay conflicting values long after the fact.
 */
export const updateUnit = (unit: Unit) => api.patch<AuthHealth>('/me', { unit });

/**
 * Writes below go through the offline queue (§8): durably stored, applied
 * optimistically, flushed when the network allows. They resolve to null when
 * the request could not be sent — that means "saved, will sync", never
 * "failed". Server-side idempotency (upsert by date, dedupe by client_uuid)
 * is what makes replaying them safe.
 */
export const putDailyLog = (date: IsoDate, patch: DailyLogPatch) =>
  enqueue<DailyLog>('PUT', `/daily-logs/${date}`, patch);

export const getDailyLogs = (from: IsoDate, to: IsoDate) =>
  api.get<DailyLog[]>(`/daily-logs?from=${from}&to=${to}`);

/**
 * The home tab's single request (§6). The date comes from this device: only it
 * knows what day it is where the user is standing, and the server is forbidden
 * from deriving it from UTC.
 */
export const getDashboard = (date: IsoDate) => api.get<Dashboard>(`/dashboard?date=${date}`);

// --- workouts --------------------------------------------------------------

export type Exercise = {
  id: number;
  name: string;
  muscle_group: string;
  equipment: string | null;
  source: 'seed' | 'custom';
};

export type WorkoutSet = {
  id: number;
  exercise_id: number;
  set_number: number;
  weight_kg: number;
  reps: number;
};

export type LastSets = {
  exercise_id: number;
  session_date: IsoDate | null;
  sets: WorkoutSet[];
};

export type WorkoutSession = {
  id: number;
  client_uuid: string;
  session_date: IsoDate;
  split: Split | null;
  notes: string | null;
  sets: WorkoutSet[];
};

export type PersonalRecord = {
  exercise_id: number;
  exercise_name: string;
  e1rm: number;
  previous_e1rm: number;
};

export type SessionSaved = {
  session: WorkoutSession;
  prs: PersonalRecord[];
};

export type SetInput = {
  exercise_id: number;
  set_number: number;
  weight_kg: number;
  reps: number;
};

export const searchExercises = (q: string) =>
  api.get<Exercise[]>(`/exercises?q=${encodeURIComponent(q)}`);

/**
 * Not queued: the caller needs the generated id to attach sets to, so this one
 * genuinely requires connectivity. Existing exercises log fine offline.
 */
export const createExercise = (body: {
  name: string;
  muscle_group: string;
  equipment?: string | null;
}) => api.post<Exercise>('/exercises', body);

export const getLastSets = (exerciseId: number) =>
  api.get<LastSets>(`/exercises/${exerciseId}/last-sets`);

export const getSessions = (from: IsoDate, to: IsoDate) =>
  api.get<WorkoutSession[]>(`/workout-sessions?from=${from}&to=${to}`);

/** Queued. `client_uuid` is the server's dedupe key, so retries are safe. */
export const saveSession = (body: {
  client_uuid: string;
  session_date: IsoDate;
  split?: Split | null;
  notes?: string | null;
  sets: SetInput[];
}) => enqueue<SessionSaved>('POST', '/workout-sessions', body);

/** Opens a new goal, closing any active one and re-baselining on the latest weight. */
export const createGoal = (goal_weight_kg: number, target_date?: IsoDate | null) =>
  api.post<Goal>('/goals', { goal_weight_kg, ...(target_date ? { target_date } : {}) });

/**
 * Moves the target of the goal already in flight. Cannot touch the baseline —
 * editing where you're heading must not reset how far you've come.
 * Omitted keys are left alone; `target_date: null` clears the date.
 */
export const updateGoal = (patch: {
  goal_weight_kg?: number;
  start_weight_kg?: number;
  target_date?: IsoDate | null;
}) => api.patch<Goal>('/goals/active', patch);

/** Resolves to null rather than throwing when no goal has been set yet. */
export async function getActiveGoal(): Promise<Goal | null> {
  try {
    return await api.get<Goal>('/goals/active');
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

// --- photos ----------------------------------------------------------------

export type Photo = {
  id: number;
  taken_on: IsoDate;
  view_url: string;
  thumb_url: string | null;
};

export type PhotoContentType = 'image/jpeg' | 'image/png' | 'image/heic';

/**
 * Not queued: the upload URL expires in ten minutes, so a request deferred
 * until connectivity returns would arrive with a dead URL. Photos need a live
 * connection by nature — the bytes have to go somewhere.
 */
export const presignPhoto = (content_type: PhotoContentType) =>
  api.post<{ upload_url: string; s3_key: string }>('/photos/presign', { content_type });

/** Queued: idempotent on s3_key server-side, so a retry cannot duplicate. */
export const confirmPhoto = (s3_key: string, taken_on: IsoDate) =>
  enqueue<Photo>('POST', '/photos', { s3_key, taken_on });

export const getPhotos = (year: number, month: number) =>
  api.get<Photo[]>(`/photos?year=${year}&month=${month}`);

export const deletePhoto = (id: number) => api.delete<void>(`/photos/${id}`);

// --- account ---------------------------------------------------------------

/** Irreversible. Not queued — the user must see it succeed or fail. */
export const deleteAccount = () =>
  api.post<{ deleted_photos: number; supabase_user_pending: boolean }>('/account/delete', {
    confirm: 'DELETE',
  });
