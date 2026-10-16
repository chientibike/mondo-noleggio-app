import { storage } from "@/src/utils/storage";

export const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL as string;
export const TOKEN_KEY = "auth_token";

let memToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

export function setToken(t: string | null) {
  memToken = t;
}
export function getToken() {
  return memToken;
}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

export async function persistToken(t: string | null) {
  memToken = t;
  if (t) await storage.secureSet(TOKEN_KEY, t);
  else await storage.secureRemove(TOKEN_KEY);
}

export async function loadToken() {
  const t = await storage.secureGet(TOKEN_KEY, null);
  memToken = typeof t === "string" ? t : null;
  return memToken;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: any } = {}): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (memToken) headers.Authorization = `Bearer ${memToken}`;
  const res = await fetch(`${BACKEND_URL}/api${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    if (res.status === 401 && memToken) onUnauthorized?.();
    let msg = "Si è verificato un errore";
    if (data?.detail) msg = typeof data.detail === "string" ? data.detail : "Dati non validi";
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export type Size = "S" | "M" | "L" | "XL";
export type Category = "gravel" | "ebike" | "gravel_muscolare";

export type Bike = {
  id: string;
  name: string;
  category: Category;
  description: string;
  image_url: string;
  price_hour: number;
  price_day: number;
  stock: Record<Size, number>;
  available: Record<Size, number>;
};

export type Booking = {
  id: string;
  user_id: string;
  user_email: string;
  user_name: string;
  bike_id: string;
  bike_name: string;
  bike_image: string;
  size: Size;
  mode: "hourly" | "daily";
  start: string;
  end: string;
  units: number;
  total: number;
  payment_method: "stripe" | "store";
  payment_status: "pending" | "paid" | "to_pay_in_store" | "failed";
  status: "pending_payment" | "confirmed" | "cancelled" | "completed";
  created_at: string;
};

export type User = { id: string; email: string; name: string; role: string; picture?: string | null };

export type Quote = { start: string; end: string; units: number; total: number; available: Record<Size, number> };
