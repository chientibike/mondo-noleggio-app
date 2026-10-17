import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { BlurView } from "expo-blur";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, imageUri, type Bike, type Quote, type Size } from "@/src/api";
import { useAuth } from "@/src/auth";
import { Button, Chip } from "@/src/components/ui";
import { CATEGORY_LABELS, CLOSE_HOUR, OPEN_HOUR, SIZES, SIZE_HEIGHTS, SPEC_KEYS, euro, fmtUnits, nextDays, specValue } from "@/src/format";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

const DAYS_OPTS = [1, 2, 3, 4, 5, 7];
const mode = "daily" as const;

export default function BikeDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const { user } = useAuth();
  const { t, lang } = useI18n();

  const days = useMemo(() => nextDays(21), [lang]); // eslint-disable-line react-hooks/exhaustive-deps
  const [date, setDate] = useState(days[0].iso);
  const [nDays, setNDays] = useState(1);
  const [size, setSize] = useState<Size | null>(null);

  const bikeQ = useQuery({ queryKey: ["bike", id], queryFn: () => api<Bike>(`/bikes/${id}`) });

  const selection = { bike_id: id, size: size ?? "M", mode, date, days: nDays, payment_method: "store" };

  const quoteQ = useQuery({
    queryKey: ["quote", id, date, nDays],
    queryFn: () => api<Quote>(`/bikes/${id}/quote`, { method: "POST", body: selection }),
    enabled: !!bikeQ.data,
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
      params: { bike_id: id, size: size ?? "M", date, days: String(nDays) },
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
        <Text style={styles.muted}>{t("bike_not_found")}</Text>
        <Button testID="bike-back-button" title={t("go_back")} variant="secondary" onPress={() => router.back()} />
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
          {bike.image_url ? (
            <Image source={{ uri: imageUri(bike.image_url) }} style={styles.heroImg} contentFit="cover" transition={200} />
          ) : (
            <View style={[styles.heroImg, styles.noImg]}>
              <Ionicons name="bicycle" size={96} color={colors.muted} />
            </View>
          )}
          <LinearGradient colors={["rgba(28,28,30,0.35)", "transparent", "rgba(28,28,30,0.8)"]} style={StyleSheetAbs} />
          <Pressable testID="bike-detail-back" onPress={() => router.back()} style={[styles.backBtn, { top: insets.top + 8 }]}>
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <View style={styles.heroText}>
            <Text style={styles.heroCat}>{CATEGORY_LABELS[bike.category]}</Text>
            <Text style={styles.heroName} testID="bike-detail-name">{bike.name}</Text>
            <Text style={styles.heroPrice}>{euro(bike.price_day)}{t("per_day")}</Text>
          </View>
        </View>

        <View style={styles.body}>
          {!!(lang === "en" && bike.description_en ? bike.description_en : bike.description) && (
            <Text style={styles.desc} testID="bike-description">{lang === "en" && bike.description_en ? bike.description_en : bike.description}</Text>
          )}
          {SPEC_KEYS.some((k) => bike.specs?.[k]) && (
            <>
              <Text style={styles.section}>{t("specs")}</Text>
              <View style={styles.specBox} testID="bike-specs">
                {SPEC_KEYS.filter((k) => bike.specs?.[k]).map((k, i) => (
                  <View key={k} style={[styles.specRow, i > 0 && styles.specDivider]}>
                    <Text style={styles.specLabel}>{t(`spec_${k}`)}</Text>
                    <Text style={styles.specValue} testID={`bike-spec-${k}`}>{specValue(bike.specs![k])}</Text>
                  </View>
                ))}
              </View>
            </>
          )}

          <Text style={styles.section}>{t("from_day")}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow} style={styles.hScroll}>
            {days.map((d) => (
              <Pressable key={d.iso} testID={`date-${d.iso}`} onPress={() => setDate(d.iso)} style={[styles.dateChip, date === d.iso && styles.dateOn]}>
                <Text style={[styles.dateDow, date === d.iso && styles.dateTextOn]}>{d.dow}</Text>
                <Text style={[styles.dateDay, date === d.iso && styles.dateTextOn]}>{d.day}</Text>
                <Text style={[styles.dateDow, date === d.iso && styles.dateTextOn]}>{d.month}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <Text style={styles.section}>{t("num_days")}</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.hRow} style={styles.hScroll}>
            {DAYS_OPTS.map((d) => (
              <Chip key={d} testID={`days-${d}`} label={fmtUnits("daily", d)} selected={nDays === d} onPress={() => setNDays(d)} />
            ))}
          </ScrollView>
          <Text style={styles.hint}>{t("daily_hint", { open: OPEN_HOUR, close: CLOSE_HOUR })}</Text>

          <View style={styles.sectionRow}>
            <Text style={styles.section}>{t("size_by_height")}</Text>
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
                    {off ? t("sold_out") : t(n === 1 ? "available_one" : "available_many", { n })}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      </ScrollView>

      <BlurView intensity={60} tint="light" style={[styles.ctaBar, { paddingBottom: insets.bottom + 16 }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.ctaLabel}>{t("total")}</Text>
          <Text style={styles.ctaTotal} testID="bike-quote-total">{quoteQ.data ? euro(quoteQ.data.total) : "—"}</Text>
        </View>
        <Button
          testID="book-now-button"
          title={size ? t("book_now") : t("choose_size")}
          disabled={!size || !quoteQ.data}
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
  noImg: { alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceTertiary },
  backBtn: { position: "absolute", left: 16, width: 44, height: 44, borderRadius: 22, backgroundColor: c.surface, alignItems: "center", justifyContent: "center" },
  heroText: { position: "absolute", left: 24, right: 24, bottom: 20 },
  heroCat: { color: c.onSurfaceInverse, fontSize: 12, fontWeight: "700", letterSpacing: 1.2, textTransform: "uppercase" },
  heroName: { color: c.onSurfaceInverse, fontSize: 28, fontWeight: "800", letterSpacing: -0.5 },
  heroPrice: { color: c.onSurfaceInverse, fontSize: 15, fontWeight: "600", marginTop: 4, opacity: 0.9 },
  body: { padding: 24, paddingTop: 20 },
  desc: { fontSize: 15, lineHeight: 22, color: c.onSurfaceSecondary },
  specBox: { backgroundColor: c.surfaceSecondary, borderRadius: 12, paddingHorizontal: 16 },
  specRow: { flexDirection: "row", justifyContent: "space-between", gap: 12, paddingVertical: 12 },
  specDivider: { borderTopWidth: 0.5, borderTopColor: c.divider },
  specLabel: { fontSize: 14, color: c.muted, flexShrink: 0 },
  specValue: { fontSize: 14, fontWeight: "600", color: c.onSurface, flexShrink: 1, textAlign: "right" },
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
