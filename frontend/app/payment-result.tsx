import { useEffect, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQueryClient } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";
import Animated, { ZoomIn } from "react-native-reanimated";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Button } from "@/src/components/ui";
import { startStripePayment } from "@/src/payments";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";

type State = "checking" | "paid" | "store" | "cancelled" | "pending" | "error";

export default function PaymentResult() {
  const p = useLocalSearchParams<{ session_id?: string; booking_id?: string; store?: string; cancelled?: string }>();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { loading, user } = useAuth();
  const [state, setState] = useState<State>(p.store ? "store" : p.cancelled ? "cancelled" : "checking");
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    if (state !== "checking" || loading || !user || !p.session_id) {
      if (!loading && state === "checking" && !p.session_id) setState("error");
      return;
    }
    let cancelled = false;
    (async () => {
      for (let i = 0; i < 10 && !cancelled; i++) {
        try {
          const r = await api<{ payment_status: string; status: string }>(`/payments/stripe/status/${p.session_id}`);
          if (r.payment_status === "paid") {
            setState("paid");
            qc.invalidateQueries({ queryKey: ["my-bookings"] });
            return;
          }
          if (r.status === "expired") {
            setState("cancelled");
            return;
          }
        } catch {
          // keep polling
        }
        await new Promise((res) => setTimeout(res, 2000));
      }
      if (!cancelled) setState("pending");
    })();
    return () => {
      cancelled = true;
    };
  }, [state, loading, user, p.session_id, qc]);

  const retry = async () => {
    if (!p.booking_id) return;
    setRetrying(true);
    try {
      const sid = await startStripePayment(p.booking_id);
      if (sid) router.replace({ pathname: "/payment-result", params: { session_id: sid, booking_id: p.booking_id } });
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setRetrying(false);
    }
  };

  const content: Record<State, { icon: any; color: string; title: string; sub: string }> = {
    checking: { icon: null, color: colors.brandPrimary, title: "Verifica del pagamento...", sub: "Attendi qualche secondo" },
    paid: { icon: "checkmark-circle", color: colors.success, title: "Prenotazione confermata!", sub: "Pagamento ricevuto. Ti aspettiamo in negozio per il ritiro." },
    store: { icon: "storefront", color: colors.brandPrimary, title: "Prenotazione confermata!", sub: "Pagherai direttamente in negozio al ritiro della bici." },
    cancelled: { icon: "close-circle", color: colors.error, title: "Pagamento annullato", sub: "La bici resta prenotata in attesa del pagamento. Puoi riprovare quando vuoi." },
    pending: { icon: "time", color: colors.warning, title: "Pagamento in elaborazione", sub: "Controlla lo stato nelle tue prenotazioni tra qualche istante." },
    error: { icon: "alert-circle", color: colors.error, title: "Qualcosa è andato storto", sub: "Controlla lo stato nelle tue prenotazioni." },
  };
  const c = content[state];

  return (
    <View style={[styles.root, { paddingTop: insets.top + 24, paddingBottom: insets.bottom + 24 }]}>
      <View style={styles.center} testID={`payment-result-${state}`}>
        {state === "checking" ? (
          <ActivityIndicator size="large" color={colors.brandPrimary} />
        ) : (
          <Animated.View entering={ZoomIn.springify()}>
            <Ionicons name={c.icon} size={88} color={c.color} />
          </Animated.View>
        )}
        <Text style={styles.title} testID="payment-result-title">{c.title}</Text>
        <Text style={styles.sub}>{c.sub}</Text>
      </View>
      <View style={styles.actions}>
        {(state === "cancelled" || state === "error") && p.booking_id && (
          <Button testID="payment-retry-button" title="Riprova pagamento" icon="card-outline" loading={retrying} onPress={retry} />
        )}
        <Button testID="go-bookings-button" title="Vai alle prenotazioni" variant={state === "cancelled" ? "ghost" : "primary"} onPress={() => router.replace("/bookings")} />
        <Button testID="go-home-button" title="Torna alle bici" variant="ghost" onPress={() => router.replace("/")} />
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface, paddingHorizontal: 24 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 16 },
  title: { fontSize: 26, fontWeight: "800", color: c.onSurface, textAlign: "center" },
  sub: { fontSize: 15, color: c.onSurfaceTertiary, textAlign: "center", lineHeight: 22, maxWidth: 320 },
  actions: { gap: 12 },
}));
