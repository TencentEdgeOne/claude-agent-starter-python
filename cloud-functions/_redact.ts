/**
 * Shared base64 redaction utilities for backend history responses.
 */

/** Matches a JSON "base64Image":"<long base64 string>" field. */
export const BASE64_IMAGE_REGEX = /"base64Image"\s*:\s*"[A-Za-z0-9+/=]{100,}"/g;

/** Placeholder used when base64Image is stripped from session/history context. */
export const IMAGE_PLACEHOLDER = '[screenshot image saved to client]';

/** Redact base64Image in a plain string (regex replacement). */
export function redactBase64InText(text: string, placeholder = IMAGE_PLACEHOLDER): string {
  if (!text.includes('base64Image')) return text;
  return text.replace(BASE64_IMAGE_REGEX, `"base64Image":"${placeholder}"`);
}
