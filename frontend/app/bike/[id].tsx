import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, type Bike, type Quote, type Size } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Button, Chip } from "@/src/components/ui";
import { CATEGORY_LABELS, CLOSE_HOUR, OPEN_HOUR, SIZES, SIZE_HEIGHTS, euro, nextDays } from "@/src/format";
import { makeStyles, useTheme } from "@/src/theme";

const HOURS_OPTS = [1, 2, 3, 4, 6, 8];
const DAYS_OPTS = [1, 2, 3, 4, 5, 7];

export default function BikeDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const { user } = useAuth();

  const days = useMemo(() => nextDays(21), []);
  const [mode, setMode] = useState<"hourly" | "daily">("hourly");
  const [date, setDate] = useState(days[0].iso);
  const [startHour, setStartHour] = useState(Math.max(OPEN_HOUR, Math.min(new Date().getHours() + 1, CLOSE_HOUR - 1)));
  const [hours, setHours] = useState(2);
  const [nDays, setNDays] = useState(1);
  const [size, setSize] = useState<Size | null>(null);

  const isToday = date === days[0].iso;
  const nowHour = new Date().getHours();
  const startHours = useMemo(() => {
    const out: number[] = [];
    for (let h = OPEN_HOUR; h < CLOSE_HOUR; h++) if (!isToday || h > nowHour) out.push(h);
    return out;
  }, [isToday, nowHour]);

  useEffect(() => {
    if (mode === "hourly" && startHours.length && !startHours.includes(startHour)) setStartHour(startHours[0]);
  }, [startHours, startHour, mode]);

  const maxHours = CLOSE_HOUR - startHour;
  useEffect(() => {
    if (hours > maxHours) setHours(Math.max(1, maxHours));
  }, [maxHours, hours]);

  const bikeQ = useQuery({ queryKey: ["bike", id], queryFn: () => api<Bike>(`/bikes/${id}`) });

  const selection = {
    bike_id: id,
    size: size ?? "M",
    mode,
    date,
    start_hour: mode === "hourly" ? startHour : undefined,
    hours: mode === "hourly" ? hours : undefined,
    days: mode === "daily" ? nDays : undefined,
    payment_method: "store",
  };
  const noSlotsToday = mode === "hourly" && startHours.length === 0;

  const quoteQ = useQuery({
    queryKey: ["quote", id, mode, date, startHour, hours, nDays],
    queryFn: () => api<Quote>(`/bikes/${id}/quote`, { method: "POST", body: selection }),
    enabled: !!bikeQ.data && !noSlotsToday,
  });

  const avail = quoteQ.data?.available;
  useEffect(() => {
    if (size && avail && (avail[size] ?? 0) <= 0) setSize(null);
  }, [avail, size]);

  const bike = bikeQ.data;
  const pendingBook = useRef(false);

  const goCheckout = () =>
    router.push({
      pathname: "/checkout",
      params: { bike_id: id, size: size ?? "M", mode, date, start_hour: String(startHour), hours: String(hours), days: String(nDays) },
    });

  // Continue the booking automatically after the user logs in from this screen.
  useEffect(() => {
    if (user && pendingBook.current && size) {
      pendingBook.current = false;
      const t = setTimeout(goCheckout, 300);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (bikeQ.isLoading) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  if (!bike) {
    return (
      <View style={[styles.root, styles.center, { padding: 24 }]}>
        <Text style={styles.muted}>Bici non trovata</Text>
        <Button testID="bike-back-button" title="Torna indietro" variant="secondary" onPress={() => router.back()} />
      </View>
    );
  }

  const book = () => {
    if (!size) return;
    if (!user) {
      pendingBook.current = true;
      router.push("/login");
      return;
    }
    goCheckout();
  };

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + 120 }} testID="bike-detail-scroll">
        <View style={styles.hero}>
          <Image source={{ uri: bike.image_url }} style={styles.heroImg} contentFit="cover" transition={200} />
          <LinearGradient colors={["rgba(28,28,30,0.35)", "transparent", "rgba(28,28,30,0.8)"]} style={StyleSheetAbs} />
          <Pressable testID="bike-detail-back" onPress={() => router.back()} style={[styles.backBtn, { top: insets.top + 8 }]}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <View style={styles.heroText}>
            <Text style={styles.heroCat}>{CATEGORY_LABELS[bike.category]}</Text>
            <Text style={styles.heroName} testID="bike-detail-name">{bike.name}</Text>
            <Text style={styles.heroPrice}>{euro(bike.price_hour)}/ora · {euro(bike.price_day)}/giorno</Text>
          </View>
        </View>

        <View style={styles.body}>
          {!!bike.description && <Text style={styles.desc}>{bike.description}</Text>}

          <Text style={styles.section}>Tipo di noleggio</Text>
          <View style={styles.segment}>
            {(["hourly", "daily"] as const).map((m) => (
              <Pressable
                key={m}
                testID={`mode-${m}`}
                onPress={() => setMode(m)}
                style={[styles.segBtn, mode === m && styles.segOn]}
              >
                <Text style={[styles.segText, mode === m && styles.segTextOn]}>{m === "hourly" ? "A ore" : "Giornata / più giorni"}</Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.section}>{mode === "hourly" ? "Giorno" : "Dal giorno"}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow} style={styles.hScroll}>
            {days.map((d) => (
              <Pressable key={d.iso} testID={`date-${d.iso}`} onPress={() => setDate(d.iso)} style={[styles.dateChip, date === d.iso && styles.dateOn]}>
                <Text style={[styles.dateDow, date === d.iso && styles.dateTextOn]}>{d.dow}</Text>
                <Text style={[styles.dateDay, date === d.iso && styles.dateTextOn]}>{d.day}</Text>
                <Text style={[styles.dateDow, date === d.iso && styles.dateTextOn]}>{d.month}</Text>
              </Pressable>
            ))}
          </ScrollView>

          {mode === "hourly" ? (
            <>
              <Text style={styles.section}>Ora di ritiro</Text>
              {noSlotsToday ? (
                <Text style={styles.muted}>Per oggi il negozio è chiuso, scegli un altro giorno.</Text>
              ) : (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow} style={styles.hScroll}>
                  {startHours.map((h) => (
                    <Chip key={h} testID={`start-hour-${h}`} label={`${h}:00`} selected={startHour === h} onPress={() => setStartHour(h)} />
                  ))}
                </ScrollView>
              )}
              <Text style={styles.section}>Durata</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow} style={styles.hScroll}>
                {HOURS_OPTS.filter((h) => h <= maxHours).map((h) => (
                  <Chip key={h} testID={`hours-${h}`} label={`${h} ${h === 1 ? "ora" : "ore"}`} selected={hours === h} onPress={() => setHours(h)} />
                ))}
              </ScrollView>
            </>
          ) : (
            <>
              <Text style={styles.section}>Numero di giorni</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow} style={styles.hScroll}>
                {DAYS_OPTS.map((d) => (
                  <Chip key={d} testID={`days-${d}`} label={`${d} ${d === 1 ? "giorno" : "giorni"}`} selected={nDays === d} onPress={() => setNDays(d)} />
                ))}
              </ScrollView>
              <Text style={styles.hint}>{`Ritiro alle ${OPEN_HOUR}:00, riconsegna entro le ${CLOSE_HOUR}:00 dell'ultimo giorno.`}</Text>
            </>
          )}

          <View style={styles.sectionRow}>
            <Text style={styles.section}>Taglia (in base alla tua altezza)</Text>
            {quoteQ.isFetching && <ActivityIndicator size="small" color={colors.brandPrimary} />}
          </View>
          <View style={styles.sizeGrid}>
            {SIZES.map((s) => {
              const n = avail?.[s] ?? 0;
              const off = !avail || n <= 0;
              return (
                <Pressable
                  key={s}
                  testID={`size-option-${s}`}
                  disabled={off}
                  onPress={() => setSize(s)}
                  style={[styles.sizeCard, size === s && styles.sizeCardOn, off && styles.sizeCardOff]}
                >
                  <Text style={[styles.sizeBig, size === s && styles.dateTextOn, off && styles.offText]}>{s}</Text>
                  <Text style={[styles.sizeH, size === s && styles.dateTextOn]}>{SIZE_HEIGHTS[s]}</Text>
                  <Text style={[styles.sizeAvail, size === s && styles.dateTextOn, off && { color: colors.error }]} testID={`size-available-${s}`}>
                    {off ? "Esaurita" : `${n} disponibil${n === 1 ? "e" : "i"}`}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      </ScrollView>

      <BlurView intensity={60} tint="light" style={[styles.ctaBar, { paddingBottom: insets.bottom + 16 }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.ctaLabel}>Totale</Text>
          <Text style={styles.ctaTotal} testID="bike-quote-total">{quoteQ.data && !noSlotsToday ? euro(quoteQ.data.total) : "—"}</Text>
        </View>
        <Button
          testID="book-now-button"
          title={size ? "Prenota ora" : "Scegli la taglia"}
          disabled={!size || noSlotsToday || !quoteQ.data}
          onPress={book}
          style={{ flex: 1.3 }}
        />
      </BlurView>
    </View>
  );
}

const StyleSheetAbs = { position: "absolute" as const, left: 0, right: 0, top: 0, bottom: 0 };

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  center: { alignItems: "center", justifyContent: "center", gap: 12 },
  muted: { color: c.muted, fontSize: 14 },
  hero: { height: 340, backgroundColor: c.surfaceTertiary },
  heroImg: { width: "100%", height: "100%" },
  backBtn: { position: "absolute", left: 16, width: 44, height: 44, borderRadius: 22, backgroundColor: c.surface, alignItems: "center", justifyContent: "center" },
  heroText: { position: "absolute", left: 24, right: 24, bottom: 20 },
  heroCat: { color: c.onSurfaceInverse, fontSize: 12, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase" },
  heroName: { color: c.onSurfaceInverse, fontSize: 28, fontWeight: "800", letterSpacing: -0.5 },
  heroPrice: { color: c.onSurfaceInverse, fontSize: 15, fontWeight: "600", marginTop: 4, opacity: 0.9 },
  body: { padding: 24, paddingTop: 20 },
  desc: { fontSize: 15, lineHeight: 22, color: c.onSurfaceSecondary },
  section: { fontSize: 13, fontWeight: "700", color: c.muted, textTransform: "uppercase", letterSpacing: 1, marginTop: 24, marginBottom: 10 },
  sectionRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  hint: { fontSize: 13, color: c.muted, marginTop: 8 },
  segment: { flexDirection: "row", backgroundColor: c.surfaceSecondary, borderRadius: 12, padding: 4 },
  segBtn: { flex: 1, height: 44, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  segOn: { backgroundColor: c.surface, shadowColor: "#000", shadowOpacity: 0.08, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  segText: { fontSize: 14, fontWeight: "600", color: c.muted },
  segTextOn: { color: c.onSurface },
  hScroll: { flexGrow: 0, marginHorizontal: -24 },
  hRow: { gap: 8, paddingHorizontal: 24 },
  dateChip: { width: 60, height: 76, borderRadius: 12, borderWidth: 1, borderColor: c.border, alignItems: "center", justifyContent: "center", flexShrink: 0 },
  dateOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  dateDow: { fontSize: 12, color: c.muted, fontWeight: "600" },
  dateDay: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  dateTextOn: { color: c.onBrandPrimary },
  sizeGrid: { flexDirection: "row", gap: 8 },
  sizeCard: { flex: 1, borderRadius: 12, borderWidth: 1, borderColor: c.border, paddingVertical: 12, alignItems: "center", gap: 2 },
  sizeCardOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  sizeCardOff: { backgroundColor: c.surfaceSecondary, borderColor: c.surfaceSecondary },
  sizeBig: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  offText: { color: c.muted },
  sizeH: { fontSize: 10, color: c.muted, textAlign: "center" },
  sizeAvail: { fontSize: 11, fontWeight: "700", color: c.success, marginTop: 4 },
  ctaBar: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: "row",
    alignItems: "center",
    gap: 16,
    paddingHorizontal: 24,
    paddingTop: 16,
    borderTopWidth: 0.5,
    borderTopColor: c.border,
    backgroundColor: "rgba(255,255,255,0.85)",
    overflow: "hidden",
  },
  ctaLabel: { fontSize: 12, color: c.muted, fontWeight: "600" },
  ctaTotal: { fontSize: 22, fontWeight: "800", color: c.onSurface },
}));
