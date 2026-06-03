import type { ChatResponse, DocumentStats } from "../types";

async function errorDetail(res: Response, fallback: string): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: string | { msg: string }[] };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      return body.detail[0].msg;
    }
  } catch {
    /* ignore parse errors */
  }
  return fallback;
}

export async function sendChat(
  message: string,
  ticker?: string
): Promise<ChatResponse> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, ticker: ticker || null }),
  });
  if (!res.ok) {
    const detail = await errorDetail(res, `Chat failed (${res.status})`);
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchDocumentStats(): Promise<DocumentStats> {
  const res = await fetch("/api/documents/stats");
  if (!res.ok) {
    throw new Error(`Stats failed: ${res.status}`);
  }
  return res.json();
}
