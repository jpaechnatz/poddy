import type { AxiosError } from 'axios';

export type ApiErrorData = {
  message?: unknown;
  error?: unknown;
  [key: string]: unknown;
};

export type HttpErrorInfo = {
  status?: number;
  message: string;
  data?: unknown;
};

const asString = (v: unknown): string | null => (typeof v === 'string' ? v : null);

// For responses without a JSON message (proxy errors, HTML error pages), say
// what the status means instead of axios' bare "Request failed with status code".
const describeStatus = (status?: number): string | null => {
  if (!status) return null;
  if (status === 502 || status === 504) {
    return `The server took too long or could not be reached (HTTP ${status}). The action may still finish in the background.`;
  }
  if (status === 503) return 'The server is busy or restarting (HTTP 503). Try again in a minute.';
  if (status === 401) return 'You are signed out (HTTP 401). Sign in again.';
  if (status === 403) return 'You are not allowed to do this (HTTP 403).';
  if (status === 404) return 'Not found (HTTP 404). It may have been deleted.';
  if (status >= 500) return `The server hit an error (HTTP ${status}). Details are in the server log.`;
  return null;
};

export const getHttpErrorInfo = (err: unknown): HttpErrorInfo => {
  const axiosErr = err as AxiosError<ApiErrorData>;
  const status = axiosErr?.response?.status;
  const data = axiosErr?.response?.data;

  const messageFromData =
    data && typeof data === 'object'
      ? asString((data as ApiErrorData).message) ?? asString((data as ApiErrorData).error)
      : null;

  return {
    status,
    data,
    message:
      messageFromData ??
      describeStatus(status) ??
      asString((axiosErr as unknown as { message?: unknown })?.message) ??
      'Request failed',
  };
};
