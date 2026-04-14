/**
 * HAWK FastAPI base URL for browser-side CRM calls.
 * Must match `NEXT_PUBLIC_API_URL` in production and be allowed by `HAWK_CORS_ORIGINS` on the API.
 */
export const CRM_API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
