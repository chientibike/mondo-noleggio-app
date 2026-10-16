import type { Booking, Category, Size } from "./api";
import { getLang, tr, type TKey } from "./i18n";

// Label maps resolve against the current language on every read.
function labels<K extends string>(prefix: string): Record<K, string> {
  return new Proxy({} as Record<K, string>, { get: (_, k) => tr(`${prefix}${String(k)}` as TKey) });
}

export const SIZES: Size[] = ["S", "M", "L", "XL"];
export const SIZE_HEIGHTS: Record<Size, string> = {
  S: "155-165 cm",
  M: "165-175 cm",
  L: "175-185 cm",
  XL: "185-195 cm",
};
export const CATEGORY_LABELS = labels<Category>("cat_");
export const OPEN_HOUR = 9;
export const CLOSE_HOUR = 19;

const DAYS_BY_LANG = {
  it: ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"],
  en: ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
};
const MONTHS_BY_LANG = {
  it: ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"],
  en: ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
};
const days = () => DAYS_BY_LANG[getLang()];
const months = () => MONTHS_BY_LANG[getLang()];

export function fmtUnits(mode: "hourly" | "daily", n: number) {
  if (mode === "hourly") return tr(n === 1 ? "hour_one" : "hour_many", { n });
  return tr(n === 1 ? "day_one" : "day_many", { n });
}

export function toISODate(d: Date) {
  const m = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${d.getFullYear()}-${m}-${day}`;
}

export function nextDays(n: number) {
  const out: { iso: string; dow: string; day: number; month: string }[] = [];
  const base = new Date();
  for (let i = 0; i < n; i++) {
    const d = new Date(base.getFullYear(), base.getMonth(), base.getDate() + i);
    out.push({ iso: toISODate(d), dow: i === 0 ? tr("today") : days()[d.getDay()], day: d.getDate(), month: months()[d.getMonth()] });
  }
  return out;
}

export function euro(v: number) {
  return `€ ${v.toFixed(2).replace(".", ",")}`;
}

// "YYYY-MM-DDTHH:MM" -> "Lun 15 Giu, 09:00"
export function fmtDateTime(s: string) {
  const [date, time] = s.split("T");
  const [y, m, d] = date.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  return `${days()[dt.getDay()]} ${d} ${months()[m - 1]}, ${time}`;
}

export function fmtRange(b: Pick<Booking, "start" | "end" | "mode">) {
  if (b.mode === "hourly") return `${fmtDateTime(b.start)} – ${b.end.split("T")[1]}`;
  return `${fmtDateTime(b.start).split(",")[0]} → ${fmtDateTime(b.end).split(",")[0]}`;
}

export const SPEC_KEYS = ["frame", "motor", "battery", "range", "suspension", "groupset", "brakes", "wheels", "weight"] as const;

// Spec values may hold "italiano / english"; show the half matching the language.
export function specValue(v: string) {
  const parts = v.split(" / ");
  if (parts.length !== 2) return v;
  return getLang() === "en" ? parts[1] : parts[0];
}

export const STATUS_LABELS = labels<Booking["status"]>("st_");
export function statusTone(b: Pick<Booking, "status">) {
  if (b.status === "cancelled") return "error" as const;
  if (b.status === "pending_payment") return "warning" as const;
  if (b.status === "completed") return "neutral" as const;
  return "success" as const;
}

export const PAYMENT_LABELS = labels<Booking["payment_status"]>("pay_");
