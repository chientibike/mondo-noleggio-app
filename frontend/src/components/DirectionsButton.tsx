import { Linking, Pressable, Text, View } from "react-native";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

export const SHOP_ADDRESS = "Contrada Le Grazie 43, Tolentino (MC)";
const MAPS_URL = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent("Contrada Le Grazie 43, 62029 Tolentino MC, Italia")}`;

export function DirectionsButton({ testID }: { testID: string }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  return (
    <Pressable
      testID={testID}
      accessibilityRole="link"
      onPress={() => Linking.openURL(MAPS_URL)}
      style={({ pressed }) => [styles.wrap, pressed && { opacity: 0.8 }]}
    >
      <View style={styles.icon}>
        <Ionicons name="navigate" size={16} color={colors.onBrandPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.title}>{t("directions")}</Text>
        <Text style={styles.addr} numberOfLines={1}>{SHOP_ADDRESS}</Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
    </Pressable>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    minHeight: 48,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 14,
    backgroundColor: c.brandTertiary,
  },
  icon: { width: 32, height: 32, borderRadius: 16, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 14, fontWeight: "700", color: c.onBrandTertiary },
  addr: { fontSize: 12, color: c.onSurfaceTertiary },
}));
