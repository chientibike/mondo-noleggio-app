import { useState } from "react";
import { ActivityIndicator, FlatList, Modal, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, type Bike, type Booking } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Badge, Button, Chip } from "@/src/components/ui";
import { CATEGORY_LABELS, PAYMENT_LABELS, SIZES, STATUS_LABELS, euro, fmtRange, statusTone } from "@/src/format";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";

type Stats = { bike_models: number; total_units: number; active_bookings: number; today_bookings: number; revenue_paid: number };
const FILTERS: { key: string; label: string }[] = [
  { key: "all", label: "Tutte" },
  { key: "confirmed", label: "Confermate" },
  { key: "pending_payment", label: "Da pagare" },
  { key: "completed", label: "Completate" },
  { key: "cancelled", label: "Annullate" },
];

export default function Admin() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [tab, setTab] = useState<"bikes" | "bookings">("bikes");
  const [filter, setFilter] = useState("all");
  const [toDelete, setToDelete] = useState<Bike | null>(null);
  const isAdmin = user?.role === "admin";

  const stats = useQuery({ queryKey: ["admin-stats"], queryFn: () => api<Stats>("/admin/stats"), enabled: isAdmin });
  const bikes = useQuery({ queryKey: ["bikes", "all"], queryFn: () => api<Bike[]>("/bikes"), enabled: isAdmin });
  const bookings = useQuery({
    queryKey: ["admin-bookings", filter],
    queryFn: () => api<Booking[]>(`/admin/bookings${filter === "all" ? "" : `?status=${filter}`}`),
    enabled: isAdmin,
  });

  const refreshAll = () => {
    qc.invalidateQueries({ queryKey: ["admin-stats"] });
    qc.invalidateQueries({ queryKey: ["admin-bookings"] });
    qc.invalidateQueries({ queryKey: ["bikes"] });
  };

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: any }) => api(`/admin/bookings/${id}`, { method: "PATCH", body }),
    onSuccess: () => {
      toast("Prenotazione aggiornata", "success");
      refreshAll();
    },
    onError: (e: any) => toast(e.message, "error"),
  });

  const del = useMutation({
    mutationFn: (id: string) => api(`/admin/bikes/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast("Bici eliminata", "success");
      refreshAll();
    },
    onError: (e: any) => toast(e.message, "error"),
    onSettled: () => setToDelete(null),
  });

  if (!isAdmin) {
    return (
      <View style={[styles.root, styles.center, { paddingTop: insets.top }]}>
        <Ionicons name="lock-closed-outline" size={44} color={colors.muted} />
        <Text style={styles.muted}>Accesso riservato agli amministratori</Text>
        <Button testID="admin-back-home" title="Torna indietro" variant="secondary" onPress={() => router.back()} />
      </View>
    );
  }

  const s = stats.data;

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <View style={styles.headRow}>
          <Pressable testID="admin-back" onPress={() => router.back()} style={styles.back}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.title}>Gestione negozio</Text>
        </View>
        <View style={styles.statsRow}>
          <Stat label="Bici in flotta" value={s ? String(s.total_units) : "—"} testID="stat-units" />
          <Stat label="Oggi" value={s ? String(s.today_bookings) : "—"} testID="stat-today" />
          <Stat label="Attive" value={s ? String(s.active_bookings) : "—"} testID="stat-active" />
          <Stat label="Incassato" value={s ? euro(s.revenue_paid) : "—"} testID="stat-revenue" />
        </View>
        <View style={styles.segment}>
          {(["bikes", "bookings"] as const).map((t) => (
            <Pressable key={t} testID={`admin-tab-${t}`} onPress={() => setTab(t)} style={[styles.segBtn, tab === t && styles.segOn]}>
              <Text style={[styles.segText, tab === t && styles.segTextOn]}>{t === "bikes" ? "Bici" : "Prenotazioni"}</Text>
            </Pressable>
          ))}
        </View>
        {tab === "bookings" && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow} contentContainerStyle={styles.chipRowContent}>
            {FILTERS.map((f) => (
              <Chip key={f.key} testID={`admin-filter-${f.key}`} label={f.label} selected={filter === f.key} onPress={() => setFilter(f.key)} />
            ))}
          </ScrollView>
        )}
      </View>

      {tab === "bikes" ? (
        <FlatList
          testID="admin-bike-list"
          data={bikes.data ?? []}
          keyExtractor={(b) => b.id}
          contentContainerStyle={[styles.list, { paddingBottom: insets.bottom + 96 }]}
          refreshControl={<RefreshControl refreshing={bikes.isRefetching} onRefresh={refreshAll} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={bikes.isLoading ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.muted}>Nessuna bici. Aggiungine una.</Text>}
          renderItem={({ item }) => (
            <View style={styles.card} testID={`admin-bike-${item.id}`}>
              <View style={styles.cardTop}>
                <Image source={{ uri: item.image_url }} style={styles.thumb} contentFit="cover" />
                <View style={{ flex: 1, gap: 2 }}>
                  <Text style={styles.name} numberOfLines={1}>{item.name}</Text>
                  <Text style={styles.meta}>{CATEGORY_LABELS[item.category]} · {euro(item.price_hour)}/h · {euro(item.price_day)}/g</Text>
                  <View style={styles.stockRow}>
                    {SIZES.map((sz) => (
                      <Text key={sz} style={styles.stock}>{sz}: <Text style={styles.stockN}>{item.stock[sz] ?? 0}</Text></Text>
                    ))}
                  </View>
                </View>
              </View>
              <View style={styles.actions}>
                <Button testID={`admin-edit-bike-${item.id}`} title="Modifica" icon="create-outline" variant="secondary" onPress={() => router.push({ pathname: "/admin/bike-form", params: { id: item.id } })} style={{ flex: 1 }} />
                <Button testID={`admin-delete-bike-${item.id}`} title="Elimina" icon="trash-outline" variant="ghost" onPress={() => setToDelete(item)} style={{ flex: 1 }} />
              </View>
            </View>
          )}
        />
      ) : (
        <FlatList
          testID="admin-booking-list"
          data={bookings.data ?? []}
          keyExtractor={(b) => b.id}
          contentContainerStyle={[styles.list, { paddingBottom: insets.bottom + 24 }]}
          refreshControl={<RefreshControl refreshing={bookings.isRefetching} onRefresh={refreshAll} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={bookings.isLoading ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.muted}>Nessuna prenotazione</Text>}
          renderItem={({ item }) => (
            <View style={styles.card} testID={`admin-booking-${item.id}`}>
              <View style={styles.rowBetween}>
                <Text style={styles.name} numberOfLines={1}>{item.bike_name} · {item.size}</Text>
                <Text style={styles.total}>{euro(item.total)}</Text>
              </View>
              <Text style={styles.meta}>{fmtRange(item)}</Text>
              <Text style={styles.meta}>{item.user_name} · {item.user_email}</Text>
              <View style={styles.badges}>
                <Badge label={STATUS_LABELS[item.status]} tone={statusTone(item)} />
                <Badge label={PAYMENT_LABELS[item.payment_status]} tone={item.payment_status === "paid" ? "brand" : "neutral"} />
              </View>
              {item.status !== "cancelled" && item.status !== "completed" && (
                <View style={styles.actions}>
                  {item.payment_status !== "paid" && (
                    <Button testID={`admin-mark-paid-${item.id}`} title="Segna pagata" variant="secondary" onPress={() => patch.mutate({ id: item.id, body: { payment_status: "paid", status: "confirmed" } })} style={{ flex: 1 }} />
                  )}
                  <Button testID={`admin-complete-${item.id}`} title="Riconsegnata" variant="secondary" onPress={() => patch.mutate({ id: item.id, body: { status: "completed" } })} style={{ flex: 1 }} />
                  <Button testID={`admin-cancel-${item.id}`} title="Annulla" variant="ghost" onPress={() => patch.mutate({ id: item.id, body: { status: "cancelled" } })} style={{ flex: 1 }} />
                </View>
              )}
            </View>
          )}
        />
      )}

      {tab === "bikes" && (
        <Pressable testID="admin-add-bike-fab" onPress={() => router.push("/admin/bike-form")} style={[styles.fab, { bottom: insets.bottom + 16 }]}>
          <Ionicons name="add" size={24} color={colors.onBrandPrimary} />
          <Text style={styles.fabText}>Aggiungi bici</Text>
        </Pressable>
      )}

      <Modal visible={!!toDelete} transparent animationType="fade" onRequestClose={() => setToDelete(null)}>
        <Pressable style={styles.backdrop} onPress={() => setToDelete(null)}>
          <Pressable style={[styles.sheet, { paddingBottom: insets.bottom + 24 }]} onPress={() => {}}>
            <Text style={styles.sheetTitle}>Eliminare {toDelete?.name}?</Text>
            <Text style={styles.muted}>Le prenotazioni esistenti resteranno nello storico.</Text>
            <Button testID="confirm-delete-bike" title="Elimina" variant="danger" loading={del.isPending} onPress={() => toDelete && del.mutate(toDelete.id)} />
            <Button testID="dismiss-delete-bike" title="Annulla" variant="ghost" onPress={() => setToDelete(null)} />
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function Stat({ label, value, testID }: { label: string; value: string; testID: string }) {
  const styles = useStyles();
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue} testID={testID} numberOfLines={1}>{value}</Text>
      <Text style={styles.statLabel} numberOfLines={1}>{label}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  center: { alignItems: "center", justifyContent: "center", gap: 12, padding: 24 },
  muted: { color: c.muted, fontSize: 14, textAlign: "center", marginTop: 8 },
  header: { backgroundColor: c.surface, paddingBottom: 12, borderBottomWidth: 0.5, borderBottomColor: c.border, gap: 12 },
  headRow: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 12 },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "800", color: c.onSurface },
  statsRow: { flexDirection: "row", gap: 8, paddingHorizontal: 16 },
  stat: { flex: 1, backgroundColor: c.brandTertiary, borderRadius: 12, padding: 10 },
  statValue: { fontSize: 17, fontWeight: "800", color: c.onBrandTertiary },
  statLabel: { fontSize: 11, color: c.onSurfaceTertiary, marginTop: 2 },
  segment: { flexDirection: "row", backgroundColor: c.surfaceSecondary, borderRadius: 12, padding: 4, marginHorizontal: 16 },
  segBtn: { flex: 1, height: 40, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  segOn: { backgroundColor: c.surface, shadowColor: "#000", shadowOpacity: 0.08, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  segText: { fontSize: 14, fontWeight: "600", color: c.muted },
  segTextOn: { color: c.onSurface },
  chipRow: { flexGrow: 0, height: 44 },
  chipRowContent: { gap: 8, paddingHorizontal: 16, alignItems: "center" },
  list: { padding: 16, gap: 12 },
  card: { backgroundColor: c.surface, borderRadius: 16, padding: 16, gap: 8 },
  cardTop: { flexDirection: "row", gap: 12, alignItems: "center" },
  thumb: { width: 64, height: 64, borderRadius: 12, backgroundColor: c.surfaceTertiary },
  name: { fontSize: 16, fontWeight: "700", color: c.onSurface, flexShrink: 1 },
  meta: { fontSize: 13, color: c.onSurfaceTertiary },
  stockRow: { flexDirection: "row", gap: 10, marginTop: 2 },
  stock: { fontSize: 12, color: c.muted },
  stockN: { fontWeight: "800", color: c.onSurface },
  actions: { flexDirection: "row", gap: 8, marginTop: 4 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  total: { fontSize: 16, fontWeight: "800", color: c.onSurface },
  badges: { flexDirection: "row", gap: 8, flexWrap: "wrap" },
  fab: {
    position: "absolute",
    right: 24,
    height: 56,
    borderRadius: 28,
    paddingHorizontal: 20,
    backgroundColor: c.brandPrimary,
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 6,
  },
  fabText: { color: c.onBrandPrimary, fontWeight: "700", fontSize: 15 },
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  sheet: { backgroundColor: c.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 24, gap: 12 },
  sheetTitle: { fontSize: 20, fontWeight: "800", color: c.onSurface },
}));
