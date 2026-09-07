/**
 * Typed fetch wrapper for the FastAPI backend.
 *
 * This is the one module allowed to hold `any` (spec §11) — it is the boundary
 * where untyped JSON becomes typed data. Everything past here is strict.
 *
 * Writes will be routed through lib/sync.ts (spec §8) once logging UI lands in
 * Phase 2; this module stays the single place that knows how to talk HTTP.
 */

import { supabase } from '@/lib/auth';
import type { IsoDate } from '@/lib/dates';

const baseUrl = process.env.EXPO_PUBLIC_API_URL;

if (!baseUrl) {
  throw new Error(
    'Missing EXPO_PUBLIC_API_URL. Copy app/.env.example to app/.env — a physical ' +
      'device cannot reach localhost, so use the laptop LAN IP.',
  );
}

export const API_URL = baseUrl.replace(/\/$/, '');

/**
 * An unreachable host does not refuse a connection, it simply never answers,
 * and `fetch` has no default timeout — so without this a wrong LAN IP spins
 * forever instead of failing. The sync queue (§8) also depends on writes
 * failing fast enough to be re-enqueued.
 */
export const REQUEST_TIMEOUT_MS = 10_000;

/**
 * Reading the session can itself stall — it may hit SecureStore and, if the
 * access token is close to expiry, a token refresh over the network. That is
 * before `fetch` is ever called, so the request timeout does not cover it.
 */
export const SESSION_TIMEOUT_MS = 8_000;

function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => setTimeout(() => reject(new ApiError(0, label)), ms)),
  ]);
}

/** An error the server described in its `{ "detail": ... }` body (spec §6). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }

  /** Worth retrying from the sync queue: the request never reached a verdict. */
  get isRetryable(): boolean {
    return this.status === 0 || this.status === 408 || this.status >= 500;
  }
}

type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  /** Skip the Authorization header (only /health needs this). */
  anonymous?: boolean;
};

function extractDetail(payload: any, fallback: string): string {
  const detail = payload?.detail;
  if (typeof detail === 'string') return detail;
  // Pydantic 422s carry an array of field-level errors.
  if (Array.isArray(detail)) {
    const first = detail[0];
    const field = Array.isArray(first?.loc) ? first.loc[first.loc.length - 1] : null;
    const message = typeof first?.msg === 'string' ? first.msg : fallback;
    return field ? `${field}: ${message}` : message;
  }
  return fallback;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, signal, anonymous = false } = options;

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  if (!anonymous) {
    const { data } = await withTimeout(
      supabase.auth.getSession(),
      SESSION_TIMEOUT_MS,
      'Timed out reading your session. Try signing out and back in.',
    );
    const token = data.session?.access_token;
    if (!token) throw new ApiError(401, 'Not signed in');
    headers.Authorization = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const onCallerAbort = () => controller.abort();
  signal?.addEventListener('abort', onCallerAbort);

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch {
    // Offline, DNS failure, wrong LAN IP — retryable, and never the user's fault.
    // A caller-driven abort is not worth reporting as a server problem.
    if (signal?.aborted) throw new ApiError(0, 'Request cancelled');
    throw new ApiError(0, `Could not reach the server at ${API_URL}. Same Wi-Fi as the laptop?`);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', onCallerAbort);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, extractDetail(payload, response.statusText));
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { method: 'GET', signal }),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: 'POST', body }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
};

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
  } | null;
  tdee: { estimate_kcal: number | null; days_of_data: number; reliable: boolean };
  volume: { muscle_group: string; sets_this_week: number; weekly_target: number }[];
  prs_recent: unknown[];
  suggestions: { id: string; kind: string; message: string; evidence: unknown }[];
  recap: unknown | null;
};

export const health = () => request<Health>('/health', { anonymous: true });
export const healthAuth = () => api.get<AuthHealth>('/health-auth');

export const putDailyLog = (date: IsoDate, patch: DailyLogPatch) =>
  api.put<DailyLog>(`/daily-logs/${date}`, patch);

export const getDailyLogs = (from: IsoDate, to: IsoDate) =>
  api.get<DailyLog[]>(`/daily-logs?from=${from}&to=${to}`);

export const getDashboard = () => api.get<Dashboard>('/dashboard');

/** Opens a new goal, closing any active one and re-baselining on the latest weight. */
export const createGoal = (goal_weight_kg: number, target_date?: IsoDate | null) =>
  api.post<Goal>('/goals', { goal_weight_kg, ...(target_date ? { target_date } : {}) });

/**
 * Moves the target of the goal already in flight. Cannot touch the baseline —
 * editing where you're heading must not reset how far you've come.
 * Omitted keys are left alone; `target_date: null` clears the date.
 */
export const updateGoal = (patch: { goal_weight_kg?: number; target_date?: IsoDate | null }) =>
  api.patch<Goal>('/goals/active', patch);

/** Resolves to null rather than throwing when no goal has been set yet. */
export async function getActiveGoal(): Promise<Goal | null> {
  try {
    return await api.get<Goal>('/goals/active');
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
