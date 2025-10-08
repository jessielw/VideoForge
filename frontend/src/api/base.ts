export const API = 'http://127.0.0.1:8000';

export interface FetchOptions {
  /** Timeout per-request in milliseconds (AbortController). */
  timeoutMs?: number;
  /** Number of retry attempts on network errors or 5xx responses. */
  retries?: number;
  /** Delay between retries in milliseconds (applies exponential backoff). */
  retryDelayMs?: number;
}

async function delay(ms: number) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchWithTimeoutAndRetry(
  endpoint: string,
  init?: RequestInit,
  opts?: FetchOptions
): Promise<Response> {
  const url = `${API}${endpoint}`;
  const timeoutMs = opts?.timeoutMs ?? 15000;
  const retries = opts?.retries ?? 0;
  const baseDelay = opts?.retryDelayMs ?? 500;

  let attempt = 0;
  while (true) {
    const controller = new AbortController();
    const timer = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : undefined;
    try {
      const resp = await fetch(url, { ...init, signal: controller.signal });
      if (timer) clearTimeout(timer);

      // Retry on server errors (5xx) when attempts remain
      if (!resp.ok && resp.status >= 500 && attempt < retries) {
        attempt++;
        const wait = baseDelay * Math.pow(2, attempt - 1);
        await delay(wait);
        continue;
      }

      return resp;
    } catch (err) {
      if (timer) clearTimeout(timer);
      // If aborted or network error, retry when attempts remain
      if (attempt < retries) {
        attempt++;
        const wait = baseDelay * Math.pow(2, attempt - 1);
        await delay(wait);
        continue;
      }
      throw err;
    }
  }
}

export async function baseFetchJson<T>(
  endpoint: string,
  init?: RequestInit,
  opts?: FetchOptions
): Promise<T> {
  const resp = await fetchWithTimeoutAndRetry(endpoint, init, opts);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return (await resp.json()) as T;
}

export async function baseFetchBlob(
  endpoint: string,
  init?: RequestInit,
  opts?: FetchOptions
): Promise<Blob> {
  const resp = await fetchWithTimeoutAndRetry(endpoint, init, opts);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(text || `Request failed: ${resp.status}`);
  }
  return await resp.blob();
}
