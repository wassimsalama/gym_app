/**
 * HTTP transport for the FastAPI backend.
 *
 * This is the one module allowed to hold `any` (spec §11) — it is the boundary
 * where untyped JSON becomes typed data. Everything past here is strict.
 *
 * Deliberately knows nothing about endpoints or the write queue, so both
 * lib/api.ts and lib/sync.ts can depend on it without depending on each other.
 */

import { supabase } from '@/lib/auth';

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
    /** Seconds the server asked us to wait, from its Retry-After header. */
    readonly retryAfterSeconds: number | null = null,
  ) {
    super(detail);
    this.name = 'ApiError';
  }

  /**
   * Worth retrying from the sync queue.
   *
   * 429 belongs here and its absence was a real bug: a rate-limited write
   * would have been treated as permanently rejected and dropped, losing the
   * user's logged workout. Being told "slow down" is the opposite of being
   * told "never ask again".
   */
  get isRetryable(): boolean {
    return this.status === 0 || this.status === 408 || this.status === 429 || this.status >= 500;
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
    // The server knows when a slot frees up; guessing would either hammer it
    // or wait far longer than necessary.
    const retryAfter = Number(response.headers.get('Retry-After'));
    throw new ApiError(
      response.status,
      extractDetail(payload, response.statusText),
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
    );
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
