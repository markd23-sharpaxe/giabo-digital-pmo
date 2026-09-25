import { AzureOpenAI } from "openai";
import { ZodError } from "zod";
import { JudgeVerdictSchema, type JudgeVerdict } from "../types/evalSchema.ts";

export function requireAzureOpenAI(): { client: AzureOpenAI; deployment: string } {
  const apiKey = process.env.AZURE_OPENAI_API_KEY;
  const endpoint = process.env.AZURE_OPENAI_ENDPOINT;
  const deployment = process.env.AZURE_OPENAI_DEPLOYMENT_NAME;
  const missing = [
    !apiKey && "AZURE_OPENAI_API_KEY",
    !endpoint && "AZURE_OPENAI_ENDPOINT",
    !deployment && "AZURE_OPENAI_DEPLOYMENT_NAME",
  ].filter(Boolean);
  if (missing.length) {
    throw new Error(`Missing Azure OpenAI env: ${missing.join(", ")}`);
  }
  const client = new AzureOpenAI({
    apiKey,
    endpoint,
    apiVersion: process.env.AZURE_OPENAI_API_VERSION ?? "2024-10-21",
    deployment,
  });
  return { client, deployment: deployment! };
}

function extractJsonObject(text: string): unknown {
  const trimmed = text.trim();
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/);
  const candidate = fenced ? fenced[1].trim() : trimmed;
  return JSON.parse(candidate);
}

function normalizeVerdictPayload(raw: unknown): unknown {
  if (!raw || typeof raw !== "object") return raw;
  const payload = raw as Record<string, unknown>;
  if (payload.justification !== undefined && typeof payload.justification !== "string") {
    payload.justification = JSON.stringify(payload.justification);
  }
  return payload;
}

export async function judgeWithAzure(
  client: AzureOpenAI,
  deployment: string,
  systemPrompt: string,
  userPayload: unknown,
): Promise<JudgeVerdict> {
  const runOnce = async (): Promise<JudgeVerdict> => {
    const response = await client.chat.completions.create({
      model: deployment,
      temperature: 0.1,
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: JSON.stringify(userPayload, null, 2) },
      ],
    });
    const text = response.choices[0]?.message?.content;
    if (!text) {
      throw new Error("Azure OpenAI judge returned empty content");
    }
    return JudgeVerdictSchema.parse(normalizeVerdictPayload(extractJsonObject(text)));
  };

  try {
    return await runOnce();
  } catch (first) {
    if (!(first instanceof ZodError) && !(first instanceof SyntaxError)) {
      throw first;
    }
    return await runOnce();
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryable(err: unknown): boolean {
  const status = typeof err === "object" && err !== null ? (err as { status?: number }).status : undefined;
  if (status === 429 || status === 500 || status === 502 || status === 503) return true;
  return /429|rate limit|timeout|ECONNRESET|503|502/i.test(String(err));
}

export async function judgeWithAzureRetry(
  client: AzureOpenAI,
  deployment: string,
  systemPrompt: string,
  userPayload: unknown,
  { maxAttempts = 4 }: { maxAttempts?: number } = {},
): Promise<JudgeVerdict> {
  let delayMs = 1000;
  let lastError: unknown;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      return await judgeWithAzure(client, deployment, systemPrompt, userPayload);
    } catch (err) {
      lastError = err;
      if (!isRetryable(err) || attempt === maxAttempts) {
        throw err;
      }
      await sleep(delayMs);
      delayMs *= 2;
    }
  }
  throw lastError;
}
