import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Modal, Pressable, RefreshControl, Text, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useFocusEffect, useRouter } from "expo-router";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, type Booking } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Button } from "@/src/components/ui";
import { PAYMENT_LABELS, STATUS_LABELS, euro, fmtRange, fmtUnits, statusTone } from "@/src/format";
import { useI18n } from "@/src/i18n";
import { startStripePayment } from "@/src/payments";
import { usesNativeTabs } from "@/src/navigation";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";

export default function BookingsScreen() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const { user, loading } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const { t } = useI18n();
  const qc = useQueryClient();
  const [toCancel, setToCancel] = useState<Booking | null>(null);
  const [paying, setPaying] = useState<string | null>(null);
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;

  const q = useQuery({ queryKey: ["my-bookings", user?.id], queryFn: () => api<Booking[]>("/bookings/me"), enabled: !!user });

  useFocusEffect(
    useCallback(() => {
      if (user) q.refetch();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [user]),
  );

  const cancel = useMutation({
    mutationFn: (id: string) => api(`/bookings/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      toast(t("booking_cancelled"), "success");
      qc.invalidateQueries({ queryKey: ["my-bookings"] });
      qc.invalidateQueries({ queryKey: ["bikes"] });
    },
    onError: (e: any) => toast(e.message, "error"),
    onSettled: () => setToCancel(null),
  });

  const pay = async (b: Booking) => {
    setPaying(b.id);
    try {
      const sid = await startStripePayment(b.id);
      if (sid) router.push({ pathname: "/payment-result", params: { session_id: sid, booking_id: b.id } });
    } catch (e: any) {
      toast(e.message, "error");
    } finally {
      setPaying(null);
    }
  };

  const header = (
    <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
      <Text style={styles.title}>{t("my_bookings")}</Text>
    </View>
  );

  if (loading) return <View style={styles.root}>{header}<ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} /></View>;

  if (!user) {
    return (
      <View style={styles.root}>
        {header}
        <View style={styles.center}>
          <Ionicons name="calendar-outline" size={48} color={colors.muted} />
          <Text style={styles.emptyTitle}>{t("login_to_see")}</Text>
          <Button testID="bookings-login-button" title={t("login")} onPress={() => router.push("/login")} />
        </View>
      </View>
    );
  }

  return (
    <View style={styles.root}>
      {header}
      {q.isLoading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
      ) : (
        <FlatList
          testID="bookings-list"
          data={q.data ?? []}
          keyExtractor={(b) => b.id}
          contentContainerStyle={[styles.list, { paddingBottom: bottomChrome + 24 }]}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={
            <View style={styles.center}>
              <Ionicons name="bicycle-outline" size={48} color={colors.muted} />
              <Text style={styles.emptyTitle}>{t("no_bookings")}</Text>
              <Text style={styles.muted}>{t("no_bookings_sub")}</Text>
              <Button testID="bookings-browse-button" title={t("browse_bikes")} onPress={() => router.push("/")} variant="secondary" />
            </View>
          }
          renderItem={({ item }) => {
            const active = item.status === "confirmed" || item.status === "pending_payment";
            return (
              <View style={styles.card} testID={`booking-card-${item.id}`}>
                <View style={styles.cardTop}>
                  <Image source={{ uri: item.bike_image }} style={styles.thumb} contentFit="cover" />
                  <View style={{ flex: 1, gap: 4 }}>
                    <Text style={styles.bikeName} numberOfLines={1}>{item.bike_name}</Text>
                    <Text style={styles.meta}>{t("size_x", { s: item.size })} · {fmtUnits(item.mode, item.units)}{item.unit_id ? ` · ${t("assigned_unit", { unit: item.unit_id })}` : ""}</Text>
                    <Text style={styles.meta}>{fmtRange(item)}</Text>
                  </View>
                  <Text style={styles.total}>{euro(item.total)}</Text>
                </View>
                <View style={styles.badges}>
                  <Badge label={STATUS_LABELS[item.status]} tone={statusTone(item)} />
                  {item.status !== "cancelled" && <Badge label={PAYMENT_LABELS[item.payment_status]} tone={item.payment_status === "paid" ? "brand" : "neutral"} />}
                </View>
                {active && (
                  <View style={styles.actions}>
                    {item.payment_method === "stripe" && item.payment_status !== "paid" && (
                      <Button testID={`booking-pay-${item.id}`} title={t("pay_now")} icon="card-outline" loading={paying === item.id} onPress={() => pay(item)} style={{ flex: 1 }} />
                    )}
                    <Button testID={`booking-cancel-${item.id}`} title={t("cancel")} variant="ghost" onPress={() => setToCancel(item)} style={{ flex: 1 }} />
                  </View>
                )}
              </View>
            );
          }}
        />
      )}

      <Modal visible={!!toCancel} transparent animationType="fade" onRequestClose={() => setToCancel(null)}>
        <Pressable style={styles.backdrop} onPress={() => setToCancel(null)}>
          <Pressable style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]} onPress={() => {}}>
            <Text style={styles.sheetTitle}>{t("cancel_q")}</Text>
            <Text style={styles.muted}>{toCancel?.bike_name} · {toCancel ? fmtRange(toCancel) : ""}</Text>
            <Button testID="confirm-cancel-button" title={t("yes_cancel")} variant="danger" loading={cancel.isPending} onPress={() => toCancel && cancel.mutate(toCancel.id)} />
            <Button testID="dismiss-cancel-button" title={t("no_keep")} variant="ghost" onPress={() => setToCancel(null)} />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  header: { paddingHorizontal: 24, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 0.5, borderBottomColor: c.border },
  title: { fontSize: 28, fontWeight: "800", color: c.onSurface, letterSpacing: -0.5 },
  center: { alignItems: "center", justifyContent: "center", gap: 12, padding: 32, marginTop: 40 },
  emptyTitle: { fontSize: 17, fontWeight: "700", color: c.onSurface, textAlign: "center" },
  muted: { color: c.muted, fontSize: 14, textAlign: "center" },
  list: { padding: 16, gap: 12 },
  card: { backgroundColor: c.surface, borderRadius: 16, padding: 16, gap: 12 },
  cardTop: { flexDirection: "row", gap: 12, alignItems: "center" },
  thumb: { width: 64, height: 64, borderRadius: 12, backgroundColor: c.surfaceTertiary },
  bikeName: { fontSize: 16, fontWeight: "700", color: c.onSurface },
  meta: { fontSize: 13, color: c.onSurfaceTertiary },
  total: { fontSize: 16, fontWeight: "800", color: c.onSurface },
  badges: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  actions: { flexDirection: "row", gap: 8 },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, gap: 12 },
  sheetTitle: { fontSize: 20, fontWeight: "800", color: c.onSurface },
}));
