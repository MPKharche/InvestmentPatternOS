export type Capabilities = {
  optional: {
    talib: boolean;
    vectorbt: boolean;
    mplfinance: boolean;
  };
  telegram: {
    mode: string;
    alerts_enabled: boolean;
    bot_token_configured: boolean;
  };
  llm: {
    disabled: boolean;
    openrouter_key_configured: boolean;
  };
};

async function safeJson(res: Response) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return { raw: text };
  }
}

export async function fetchCapabilities(): Promise<Capabilities> {
  const res = await fetch(`/api/v1/meta/capabilities`, { cache: "no-store" });
  if (!res.ok) {
    const j = await safeJson(res);
    throw new Error(`Capabilities failed (${res.status}): ${JSON.stringify(j)}`);
  }
  return (await res.json()) as Capabilities;
}

export async function fetchHealth(): Promise<{ status: string; version?: string }> {
  const res = await fetch(`/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Health failed (${res.status})`);
  return (await res.json()) as { status: string; version?: string };
}

