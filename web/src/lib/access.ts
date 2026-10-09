/** Live-run access code: typed once in the dialog, or carried in a judge link as ?code=... */
const KEY = "pg-code";

export function savedCode(): string {
  try {
    return localStorage.getItem(KEY) || sessionStorage.getItem(KEY) || "";
  } catch {
    return "";
  }
}

export function saveCode(code: string) {
  try {
    localStorage.setItem(KEY, code);
    sessionStorage.setItem(KEY, code);
  } catch {
    /* storage unavailable: the dialog will ask again */
  }
}

/** Reads ?code= from the address bar, stores it, and removes it from the visible URL. */
export function captureCodeFromUrl(): boolean {
  const url = new URL(location.href);
  const code = url.searchParams.get("code");
  if (!code || !/^[\w-]{4,64}$/.test(code)) return false;
  saveCode(code);
  url.searchParams.delete("code");
  history.replaceState({}, "", url.pathname + (url.search ? url.search : "") + url.hash);
  return true;
}
