/**
 * Turning an error into something worth showing a user.
 *
 * The distinction that matters is whether the request reached the server. A
 * connectivity failure and a rejected request need different words and send the
 * user to different places — labelling everything "Offline" once had someone
 * checking their Wi-Fi over a stale app bundle.
 */

import { ApiError } from '@/lib/http';

export type DisplayError = {
  title: string;
  detail: string;
  /** True only when the request never reached the server. */
  offline: boolean;
};

export function describeError(error: unknown, fallback: string): DisplayError {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return { title: 'Offline', detail: error.detail, offline: true };
    }
    if (error.status === 401) {
      return { title: 'Signed out', detail: 'Sign in again to continue.', offline: false };
    }
    if (error.status >= 500) {
      return { title: 'Server error', detail: error.detail, offline: false };
    }
    return { title: "Couldn't load", detail: error.detail, offline: false };
  }
  return { title: 'Something went wrong', detail: fallback, offline: false };
}
