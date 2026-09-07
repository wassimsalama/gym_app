/**
 * Uploading a progress photo (spec §9).
 *
 * Compression happens on the device before anything leaves it: the longest edge
 * is capped at 2048 px at ~0.8 quality. A modern phone photo is 3–5 MB and a
 * progress shot does not need that — this keeps uploads quick on gym wifi and
 * the bucket close to free.
 */

import * as ImageManipulator from 'expo-image-manipulator';

import { confirmPhoto, presignPhoto, type Photo } from '@/lib/api';
import type { IsoDate } from '@/lib/dates';
import { ApiError } from '@/lib/http';

export const MAX_EDGE_PX = 2048;
export const JPEG_QUALITY = 0.8;

export async function compress(uri: string): Promise<string> {
  const context = ImageManipulator.ImageManipulator.manipulate(uri);
  context.resize({ width: MAX_EDGE_PX });

  const image = await context.renderAsync();
  const result = await image.saveAsync({
    compress: JPEG_QUALITY,
    format: ImageManipulator.SaveFormat.JPEG,
  });

  return result.uri;
}

/**
 * Compress, upload straight to the bucket, then tell the API it exists.
 *
 * The bytes never pass through our server. The confirm call is queued, so a
 * connection that dies between the upload and the confirm still resolves — the
 * object is already in the bucket and the row follows when signal returns.
 */
export async function uploadPhoto(uri: string, takenOn: IsoDate): Promise<Photo | null> {
  const compressed = await compress(uri);
  const { upload_url, s3_key } = await presignPhoto('image/jpeg');

  const body = await fetch(compressed).then((response) => response.blob());
  const upload = await fetch(upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': 'image/jpeg' },
    body,
  });

  if (!upload.ok) {
    throw new ApiError(upload.status, 'The upload was rejected. Try again.');
  }

  return confirmPhoto(s3_key, takenOn);
}
