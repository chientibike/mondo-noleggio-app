import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, type Bike, type Booking, type Quote } from "@/src/api";
import { Button } from "@/src/components/ui";
import { SIZE_HEIGHTS, euro, fmtRange } from "@/src/format";
import { startStripePayment } from "@/src/payments";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";

type Method = "stripe" | "store";

export default function Checkout() {
  const p = useLocalSearchParams<{ bike_id: string; size: string; mode: "hourly" | "daily"; date: string; start_hour: string; hours: string; days: string }>();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const [method, setMethod] = useState<Method>("stripe");
  const [busy, setBusy] = useState(false);

  const body = {
    bike_id: p.bike_id,
    size: p.size,
    mode: p.mode,
    date: p.date,
    start_hour: p.mode === "hourly" ? Number(p.start_hour) : undefined,
    hours: p.mode === "hourly" ? Number(p.hours) : undefined,
    days: p.mode === "daily" ? Number(p.days) : undefined,
  };

  const bikeQ = useQuery({ queryKey: ["bike", p.bike_id], queryFn: () => api<Bike>(`/bikes/${p.bike_id}`) });
  const quoteQ = useQuery({
    queryKey: ["quote-checkout", body],
    queryFn: () => api<Quote>(`/bikes/${p.bike_id}/quote`, { method: "POST", body: { ...body, payment_method: "store" } }),
  });

  const confirm = async () => {
    setBusy(true);
    try {
      const booking = await api<Booking>("/bookings", { method: "POST", body: { ...body, payment_method: method } });
      qc.invalidateQueries({ queryKey: ["my-bookings"] });
      qc.invalidateQueries({ queryKey: ["quote"] });
      if (method === "store") {
        router.replace({ pathname: "/payment-result", params: { booking_id: booking.id, store: "1" } });
        return;
      }
      const sid = await startStripePayment(booking.id);
      if (sid) router.replace({ pathname: "/payment-result", params: { session_id: sid, booking_id: booking.id } });
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  };

  const bike = bikeQ.data;
  const quote = quoteQ.data;

  const methods: { key: Method | "paypal"; title: string; sub: string; icon: any; disabled?: boolean }[] = [
    { key: "stripe", title: "Paga ora con carta", sub: "Pagamento sicuro con Stripe", icon: "card-outline" },
    { key: "store", title: "Paga in negozio", sub: "Paghi al ritiro della bici", icon: "storefront-outline" },
    { key: "paypal", title: "PayPal", sub: "Presto disponibile", icon: "logo-paypal", disabled: true },
  ];

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="checkout-back" onPress={() => router.back()} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Conferma prenotazione</Text>
      </View>

      {!bike || !quote ? (
        <View style={styles.center}>
          {quoteQ.isError ? (
            <>
              <Text style={styles.muted}>{(quoteQ.error as Error).message}</Text>
              <Button testID="checkout-retry" title="Riprova" variant="secondary" onPress={() => quoteQ.refetch()} />
            </>
          ) : (
            <ActivityIndicator color={colors.brandPrimary} />
          )}
        </View>
      ) : (
        <ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 120 }]}>
          <View style={styles.summary} testID="checkout-summary">
            <Image source={{ uri: bike.image_url }} style={styles.thumb} contentFit="cover" />
            <View style={{ flex: 1, gap: 4 }}>
              <Text style={styles.bikeName}>{bike.name}</Text>
              <Text style={styles.meta}>Taglia {p.size} · {SIZE_HEIGHTS[p.size as keyof typeof SIZE_HEIGHTS]}</Text>
            </View>
          </View>
          <View style={styles.box}>
            <Row label="Quando" value={fmtRange({ start: quote.start, end: quote.end, mode: p.mode })} />
            <Row label="Durata" value={p.mode === "hourly" ? `${quote.units} ${quote.units === 1 ? "ora" : "ore"}` : `${quote.units} ${quote.units === 1 ? "giorno" : "giorni"}`} />
            <Row label="Tariffa" value={p.mode === "hourly" ? `${euro(bike.price_hour)}/ora` : `${euro(bike.price_day)}/giorno`} />
            <View style={styles.divider} />
            <View style={styles.rowLine}>
              <Text style={styles.totalLabel}>Totale</Text>
              <Text style={styles.total} testID="checkout-total">{euro(quote.total)}</Text>
            </View>
          </View>

          <Text style={styles.section}>Metodo di pagamento</Text>
          {methods.map((m) => {
            const on = method === m.key;
            return (
              <Pressable
                key={m.key}
                testID={`payment-method-${m.key}`}
                disabled={m.disabled}
                onPress={() => setMethod(m.key as Method)}
                style={[styles.method, on && styles.methodOn, m.disabled && { opacity: 0.5 }]}
              >
                <Ionicons name={m.icon} size={24} color={on ? colors.brandPrimary : colors.onSurfaceTertiary} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.methodTitle}>{m.title}</Text>
                  <Text style={styles.meta}>{m.sub}</Text>
                </View>
                <Ionicons name={on ? "radio-button-on" : "radio-button-off"} size={22} color={on ? colors.brandPrimary : colors.borderStrong} />
              </Pressable>
            );
          })}
        </ScrollView>
      )}

      <View style={[styles.ctaBar, { paddingBottom: insets.bottom + 16 }]}>
        <Button
          testID="confirm-booking-button"
          title={method === "stripe" ? "Conferma e paga" : "Conferma prenotazione"}
          loading={busy}
          disabled={!quote || (quote.available?.[p.size as "S"] ?? 0) <= 0}
          onPress={confirm}
        />
      </View>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  const styles = useStyles();
  return (
    <View style={styles.rowLine}>
      <Text style={styles.meta}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  header: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 0.5, borderBottomColor: c.border },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12, padding: 24 },
  muted: { color: c.muted, fontSize: 14, textAlign: "center" },
  content: { padding: 16, gap: 12 },
  summary: { backgroundColor: c.surface, borderRadius: 16, padding: 12, flexDirection: "row", gap: 12, alignItems: "center" },
  thumb: { width: 72, height: 72, borderRadius: 12, backgroundColor: c.surfaceTertiary },
  bikeName: { fontSize: 17, fontWeight: "700", color: c.onSurface },
  meta: { fontSize: 13, color: c.onSurfaceTertiary },
  box: { backgroundColor: c.surface, borderRadius: 16, padding: 16, gap: 10 },
  rowLine: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 12 },
  value: { fontSize: 14, fontWeight: "600", color: c.onSurface, flexShrink: 1, textAlign: "right" },
  divider: { height: 0.5, backgroundColor: c.divider, marginVertical: 4 },
  totalLabel: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  total: { fontSize: 22, fontWeight: "800", color: c.onSurface },
  section: { fontSize: 13, fontWeight: "700", color: c.muted, textTransform: "uppercase", letterSpacing: 1, marginTop: 12, marginLeft: 4 },
  method: { backgroundColor: c.surface, borderRadius: 16, padding: 16, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1.5, borderColor: c.surface },
  methodOn: { borderColor: c.brandPrimary },
  methodTitle: { fontSize: 15, fontWeight: "700", color: c.onSurface },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: 24, paddingTop: 16, backgroundColor: c.surface, borderTopWidth: 0.5, borderTopColor: c.border },
}));
