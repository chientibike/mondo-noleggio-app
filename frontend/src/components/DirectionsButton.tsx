import { Linking, Pressable, Text, View } from "react-native";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

export const SHOP_ADDRESS = "Contrada Le Grazie 43, Tolentino (MC)";
const MAPS_URL = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent("Contrada Le Grazie 43, 62029 Tolentino MC, Italia")}`;

const WHATSAPP_URL = `https://wa.me/393289832243?text=${encodeURIComponent("Ciao! Vi scrivo dall'app Mondo Noleggio: ")}`;
const WHATSAPP_GREEN = "#25D366"; // WhatsApp brand colour, same in light and dark

/** "Come arrivare" + WhatsApp chat with the shop, side by side. */
export function ShopContactRow({ prefix }: { prefix: string }) {
  const styles = useStyles();
  const { t } = useI18n();
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <DirectionsButton testID={`${prefix}-directions-button`} />
      </View>
      <Pressable
        testID={`${prefix}-whatsapp-button`}
        accessibilityRole="link"
        accessibilityLabel={t("whatsapp")}
        onPress={() => Linking.openURL(WHATSAPP_URL)}
        style={({ pressed }) => [styles.wa, pressed && { opacity: 0.8 }]}
      >
        <Ionicons name="logo-whatsapp" size={22} color="#FFFFFF" />
        <Text style={styles.waText}>{t("whatsapp")}</Text>
      </Pressable>
    </View>
  );
}

function DirectionsButton({ testID }: { testID: string }) {
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
  row: { flexDirection: "row", gap: 8, alignItems: "stretch" },
  wa: { minHeight: 48, paddingHorizontal: 12, borderRadius: 14, backgroundColor: WHATSAPP_GREEN, alignItems: "center", justifyContent: "center", gap: 2 },
  waText: { fontSize: 11, fontWeight: "700", color: "#FFFFFF" },
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
