/** Parse FastAPI `{ "detail": "..." }` or validation error arrays from a failed fetch Response. */
export async function readApiErrorResponse(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const j = JSON.parse(text) as { detail?: string | { msg?: string }[] };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) {
      const parts = j.detail.map((x) =>
        typeof x === "object" && x && "msg" in x ? String((x as { msg?: string }).msg) : "",
      );
      const joined = parts.filter(Boolean).join("; ");
      if (joined) return joined;
    }
  } catch {
    /* not JSON */
  }
  return text.trim().slice(0, 280) || `Request failed (${res.status})`;
}
