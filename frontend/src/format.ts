import type { Booking, Category, Size } from "./api";

export const SIZES: Size[] = ["S", "M", "L", "XL"];
export const SIZE_HEIGHTS: Record<Size, string> = {
  S: "155-165 cm",
  M: "165-175 cm",
  L: "175-185 cm",
  XL: "185-195 cm",
};
export const CATEGORY_LABELS: Record<Category, string> = {
  gravel: "Gravel",
  ebike: "E-bike",
  gravel_muscolare: "Gravel muscolare",
};
export const OPEN_HOUR = 9;
export const CLOSE_HOUR = 19;

const DAYS = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];
const MONTHS = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];

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
    out.push({ iso: toISODate(d), dow: i === 0 ? "Oggi" : DAYS[d.getDay()], day: d.getDate(), month: MONTHS[d.getMonth()] });
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
  return `${DAYS[dt.getDay()]} ${d} ${MONTHS[m - 1]}, ${time}`;
}

export function fmtRange(b: Pick<Booking, "start" | "end" | "mode">) {
  if (b.mode === "hourly") return `${fmtDateTime(b.start)} – ${b.end.split("T")[1]}`;
  return `${fmtDateTime(b.start).split(",")[0]} → ${fmtDateTime(b.end).split(",")[0]}`;
}

export const STATUS_LABELS: Record<Booking["status"], string> = {
  pending_payment: "In attesa di pagamento",
  confirmed: "Confermata",
  cancelled: "Annullata",
  completed: "Completata",
};
export function statusTone(b: Pick<Booking, "status">) {
  if (b.status === "cancelled") return "error" as const;
  if (b.status === "pending_payment") return "warning" as const;
  if (b.status === "completed") return "neutral" as const;
  return "success" as const;
}

export const PAYMENT_LABELS: Record<Booking["payment_status"], string> = {
  pending: "Da pagare online",
  paid: "Pagata",
  to_pay_in_store: "Paga in negozio",
  failed: "Pagamento fallito",
};
