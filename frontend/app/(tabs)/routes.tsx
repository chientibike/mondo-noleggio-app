import { Linking, Pressable, ScrollView, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { useI18n } from "@/src/i18n";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, useTheme } from "@/src/theme";

const STRAVA_URL = "https://www.strava.com/athlete/routes";
const STRAVA_ORANGE = "#FC4C02"; // Strava brand colour, same in light and dark
const INSTAGRAM_URL = "https://www.instagram.com/chientibike/";
const INSTAGRAM_PINK = "#E1306C"; // Instagram brand colour, same in light and dark

export default function RoutesScreen() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>{t("routes_title")}</Text>
      </View>
      <ScrollView contentContainerStyle={[styles.body, { paddingBottom: bottomChrome + 24 }]}>
        <View style={styles.hero}>
          <Ionicons name="map-outline" size={44} color={colors.brandPrimary} />
          <Text style={styles.heroTitle}>{t("routes_heading")}</Text>
          <Text style={styles.heroText}>{t("routes_text")}</Text>
        </View>
        <Pressable
          testID="strava-link-button"
          accessibilityRole="link"
          onPress={() => Linking.openURL(STRAVA_URL)}
          style={({ pressed }) => [styles.strava, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="navigate-circle" size={24} color="#FFFFFF" />
          <Text style={styles.stravaText}>{t("routes_strava")}</Text>
          <Ionicons name="open-outline" size={18} color="#FFFFFF" />
        </Pressable>
        <Pressable
          testID="instagram-link-button"
          accessibilityRole="link"
          onPress={() => Linking.openURL(INSTAGRAM_URL)}
          style={({ pressed }) => [styles.strava, { backgroundColor: INSTAGRAM_PINK }, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="logo-instagram" size={24} color="#FFFFFF" />
          <Text style={styles.stravaText}>{t("routes_instagram")}</Text>
          <Ionicons name="open-outline" size={18} color="#FFFFFF" />
        </Pressable>
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  header: { paddingHorizontal: 24, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 0.5, borderBottomColor: c.border },
  title: { fontSize: 28, fontWeight: "800", color: c.onSurface, letterSpacing: -0.5 },
  body: { padding: 24, gap: 16 },
  hero: { backgroundColor: c.surface, borderRadius: 20, padding: 24, gap: 12, alignItems: "center" },
  heroTitle: { fontSize: 20, fontWeight: "800", color: c.onSurface, textAlign: "center" },
  heroText: { fontSize: 15, color: c.onSurfaceTertiary, textAlign: "center", lineHeight: 22 },
  strava: {
    minHeight: 56,
    borderRadius: 16,
    backgroundColor: STRAVA_ORANGE,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 10,
    paddingHorizontal: 20,
  },
  stravaText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
}));
