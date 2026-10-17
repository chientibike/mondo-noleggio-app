import { useState } from "react";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, imageUri, type Bike, type Category } from "@/src/api";
import { CATEGORY_LABELS, SIZES, euro } from "@/src/format";
import { Button, Chip } from "@/src/components/ui";
import { ShopContactRow } from "@/src/components/DirectionsButton";
import { useAuth } from "@/src/auth";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";

const CATS: (Category | "all")[] = ["all", "gravel", "egravel", "ebike_mtb"];

export default function CatalogScreen() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const { user } = useAuth();
  const { t } = useI18n();
  const [cat, setCat] = useState<Category | "all">("all");
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;

  const q = useQuery({
    queryKey: ["bikes", cat],
    queryFn: () => api<Bike[]>(`/bikes${cat === "all" ? "" : `?category=${cat}`}`),
  });

  const bikes = q.data ?? [];

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <View style={styles.titleRow}>
          <Image source={require("@/assets/images/logo.png")} style={styles.logo} contentFit="contain" testID="app-logo" />
          <View style={{ flex: 1 }}>
            <Text style={styles.kicker}>Mondo Noleggio</Text>
            <Text style={styles.title} testID="catalog-title">{t("choose_bike")}</Text>
          </View>
          <Pressable testID="header-profile-button" onPress={() => router.push(user ? "/profile" : "/login")} style={styles.avatar}>
            {user?.picture ? (
              <Image source={{ uri: user.picture }} style={styles.avatarImg} />
            ) : (
              <Ionicons name="person" size={20} color={colors.onBrandSecondary} />
            )}
          </Pressable>
        </View>
        <View style={styles.directions}>
          <ShopContactRow prefix="home" />
        </View>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.chipRow}
          contentContainerStyle={styles.chipRowContent}
        >
          {CATS.map((c) => (
            <Chip
              key={c}
              testID={`category-chip-${c}`}
              label={c === "all" ? t("all") : CATEGORY_LABELS[c]}
              selected={cat === c}
              onPress={() => setCat(c)}
            />
          ))}
        </ScrollView>
      </View>

      {q.isLoading ? (
        <View style={styles.center} testID="catalog-loading">
          <ActivityIndicator color={colors.brandPrimary} />
          <Text style={styles.muted}>{t("loading_bikes")}</Text>
        </View>
      ) : q.isError ? (
        <View style={styles.center}>
          <Ionicons name="cloud-offline-outline" size={40} color={colors.muted} />
          <Text style={styles.muted}>{t("load_error")}</Text>
          <Button testID="catalog-retry-button" title={t("retry")} onPress={() => q.refetch()} variant="secondary" />
        </View>
      ) : (
        <FlatList
          testID="bike-list"
          data={bikes}
          keyExtractor={(b) => b.id}
          contentContainerStyle={[styles.list, { paddingBottom: bottomChrome + 24 }]}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={
            <View style={styles.center}>
              <Ionicons name="bicycle-outline" size={44} color={colors.muted} />
              <Text style={styles.muted}>{t("no_bikes")}</Text>
              <Button testID="catalog-empty-reload" title={t("reload")} variant="secondary" onPress={() => q.refetch()} />
            </View>
          }
          renderItem={({ item, index }) => <BikeCard bike={item} index={index} onPress={() => router.push(`/bike/${item.id}`)} />}
        />
      )}
    </View>
  );
}

function BikeCard({ bike, index, onPress }: { bike: Bike; index: number; onPress: () => void }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const total = SIZES.reduce((a, s) => a + (bike.stock[s] ?? 0), 0);
  return (
    <Animated.View entering={FadeInDown.delay(index * 60).springify()}>
      <Pressable testID={`bike-card-${bike.id}`} onPress={onPress} style={({ pressed }) => [styles.card, pressed && { transform: [{ scale: 0.985 }] }]}>
        <View style={styles.imgWrap}>
          {bike.image_url ? (
            <Image source={{ uri: imageUri(bike.image_url) }} style={styles.img} contentFit="cover" transition={200} />
          ) : (
            <View style={[styles.img, styles.noImg]} testID={`bike-card-noimg-${bike.id}`}>
              <Ionicons name="bicycle" size={64} color={colors.muted} />
            </View>
          )}
          <LinearGradient colors={["transparent", "rgba(28,28,30,0.75)"]} style={styles.scrim} />
          <View style={styles.imgOverlay}>
            <Text style={styles.cardCat}>{CATEGORY_LABELS[bike.category]}</Text>
            <Text style={styles.cardName} numberOfLines={1}>{bike.name}</Text>
          </View>
        </View>
        <View style={styles.cardBody}>
          <View style={styles.sizeTags}>
            {SIZES.map((s) => {
              const n = bike.stock[s] ?? 0;
              return (
                <View key={s} style={[styles.sizeTag, n === 0 && styles.sizeTagOff]}>
                  <Text style={[styles.sizeTagText, n === 0 && { color: colors.muted }]}>{s}</Text>
                </View>
              );
            })}
            <Text style={styles.units}>{t("in_fleet", { n: total })}</Text>
          </View>
          <View style={styles.prices}>
            <Text style={styles.price} testID={`bike-price-day-${bike.id}`}>{euro(bike.price_day)}<Text style={styles.per}>{t("per_day")}</Text></Text>
          </View>
        </View>
      </Pressable>
    </Animated.View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { backgroundColor: c.surface, borderBottomWidth: 0.5, borderBottomColor: c.border },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 24, marginBottom: 8 },
  logo: { width: 52, height: 52 },
  directions: { paddingHorizontal: 24, paddingBottom: 4 },
  kicker: { fontSize: 12, fontWeight: "700", color: c.brand, letterSpacing: 1.2, textTransform: "uppercase" },
  title: { fontSize: 28, fontWeight: "800", color: c.onSurface, letterSpacing: -0.5 },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: 44, height: 44 },
  chipRow: { flexGrow: 0, height: 52 },
  chipRowContent: { gap: 8, paddingHorizontal: 24, alignItems: "center" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12, padding: 32, minHeight: 300 },
  muted: { color: c.muted, fontSize: 14 },
  list: { padding: 16, paddingHorizontal: 24, gap: 20 },
  card: {
    backgroundColor: c.surface,
    borderRadius: 20,
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 3,
  },
  imgWrap: { height: 200, borderTopLeftRadius: 20, borderTopRightRadius: 20, overflow: "hidden", backgroundColor: c.surfaceTertiary },
  img: { width: "100%", height: "100%" },
  noImg: { alignItems: "center", justifyContent: "center", paddingBottom: 40, backgroundColor: c.surfaceTertiary },
  scrim: { position: "absolute", left: 0, right: 0, bottom: 0, height: 120 },
  imgOverlay: { position: "absolute", left: 16, right: 16, bottom: 14 },
  cardCat: { color: c.onSurfaceInverse, fontSize: 12, fontWeight: "700", textTransform: "uppercase", letterSpacing: 1, opacity: 0.9 },
  cardName: { color: c.onSurfaceInverse, fontSize: 20, fontWeight: "800" },
  cardBody: { padding: 16, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 },
  sizeTags: { flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 1, flexWrap: "wrap" },
  sizeTag: { width: 30, height: 26, borderRadius: 6, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  sizeTagOff: { backgroundColor: c.surfaceSecondary },
  sizeTagText: { fontSize: 12, fontWeight: "700", color: c.onBrandTertiary },
  units: { fontSize: 12, color: c.muted, marginLeft: 4 },
  prices: { alignItems: "flex-end" },
  price: { fontSize: 18, fontWeight: "800", color: c.onSurface },
  priceDay: { fontSize: 13, fontWeight: "600", color: c.onSurfaceTertiary },
  per: { fontSize: 12, fontWeight: "500", color: c.muted },
}));
