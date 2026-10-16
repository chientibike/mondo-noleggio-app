import { Platform } from "react-native";
import * as WebBrowser from "expo-web-browser";

import { api, BACKEND_URL } from "./api";

// Opens Stripe Checkout. Returns the session id on native (after the browser closes);
// on web the page navigates away and the result screen handles the return.
export async function startStripePayment(bookingId: string): Promise<string | null> {
  const returnUrl =
    Platform.OS === "web" ? `${window.location.origin}/payment-result` : `${BACKEND_URL}/api/payments/return`;
  const res = await api<{ url: string; session_id: string }>("/payments/stripe/checkout", {
    method: "POST",
    body: { booking_id: bookingId, return_url: returnUrl },
  });
  if (Platform.OS === "web") {
    window.location.href = res.url;
    return null;
  }
  await WebBrowser.openBrowserAsync(res.url);
  return res.session_id;
}
