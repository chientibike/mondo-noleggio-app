import { Pressable, ScrollView, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Image } from "expo-image";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { useAuth } from "@/src/auth";
import { Button, Chip } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { SIZES, SIZE_HEIGHTS, OPEN_HOUR, CLOSE_HOUR } from "@/src/format";
import { usesNativeTabs } from "@/src/navigation";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const { user, logout } = useAuth();
  const router = useRouter();
  const toast = useToast();
  const { t, lang, setLang } = useI18n();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 12 }]}>
        <Text style={styles.title}>{t("profile")}</Text>
      </View>
      <ScrollView contentContainerStyle={[styles.content, { paddingBottom: bottomChrome + 24 }]}>
        {user ? (
          <View style={styles.card} testID="profile-card">
            <View style={styles.avatar}>
              {user.picture ? (
                <Image source={{ uri: user.picture }} style={styles.avatarImg} />
              ) : (
                <Text style={styles.avatarText}>{user.name.slice(0, 1).toUpperCase()}</Text>
              )}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.name} testID="profile-name">{user.name}</Text>
              <Text style={styles.muted} testID="profile-email">{user.email}</Text>
              {user.role === "admin" && <Text style={styles.adminTag}>{t("admin_role")}</Text>}
            </View>
          </View>
        ) : (
          <View style={styles.card}>
            <Ionicons name="person-circle-outline" size={48} color={colors.muted} />
            <View style={{ flex: 1, gap: 8 }}>
              <Text style={styles.name}>{t("not_logged")}</Text>
              <Button testID="profile-login-button" title={t("login_or_register")} onPress={() => router.push("/login")} />
            </View>
          </View>
        )}

        {user?.role === "admin" && (
          <Pressable testID="admin-area-button" style={styles.row} onPress={() => router.push("/admin")}>
            <Ionicons name="construct-outline" size={22} color={colors.brandPrimary} />
            <Text style={styles.rowText}>{t("admin_area")}</Text>
            <Ionicons name="chevron-forward" size={20} color={colors.muted} />
          </Pressable>
        )}

        <Text style={styles.section}>{t("language")}</Text>
        <View style={[styles.box, styles.langRow]}>
          <Chip testID="language-it" label="Italiano" selected={lang === "it"} onPress={() => setLang("it")} />
          <Chip testID="language-en" label="English" selected={lang === "en"} onPress={() => setLang("en")} />
        </View>

        <Text style={styles.section}>{t("size_guide")}</Text>
        <View style={styles.box}>
          {SIZES.map((s) => (
            <View key={s} style={styles.sizeRow}>
              <View style={styles.sizePill}><Text style={styles.sizePillText}>{s}</Text></View>
              <Text style={styles.rowText}>{t("height", { h: SIZE_HEIGHTS[s] })}</Text>
            </View>
          ))}
        </View>

        <Text style={styles.section}>{t("shop_hours")}</Text>
        <View style={styles.box}>
          <View style={styles.sizeRow}>
            <Ionicons name="time-outline" size={20} color={colors.brandPrimary} />
            <Text style={styles.rowText}>{t("every_day", { o: OPEN_HOUR, c: CLOSE_HOUR })}</Text>
          </View>
        </View>

        {user && (
          <Button
            testID="logout-button"
            title={t("logout")}
            variant="ghost"
            icon="log-out-outline"
            onPress={async () => {
              await logout();
              toast(t("logged_out"), "info");
            }}
            style={{ marginTop: 8 }}
          />
        )}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surfaceSecondary },
  header: { paddingHorizontal: 24, paddingBottom: 12, backgroundColor: c.surface, borderBottomWidth: 0.5, borderBottomColor: c.border },
  title: { fontSize: 28, fontWeight: "800", color: c.onSurface, letterSpacing: -0.5 },
  content: { padding: 16, gap: 12 },
  card: { backgroundColor: c.surface, borderRadius: 16, padding: 16, flexDirection: "row", alignItems: "center", gap: 16 },
  avatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center", overflow: "hidden" },
  avatarImg: { width: 56, height: 56 },
  avatarText: { fontSize: 22, fontWeight: "800", color: c.onBrandSecondary },
  name: { fontSize: 17, fontWeight: "700", color: c.onSurface },
  muted: { fontSize: 14, color: c.muted },
  adminTag: { marginTop: 4, fontSize: 12, fontWeight: "700", color: c.brand },
  row: { backgroundColor: c.surface, borderRadius: 16, padding: 16, flexDirection: "row", alignItems: "center", gap: 12, minHeight: 56 },
  rowText: { flex: 1, fontSize: 15, color: c.onSurface, fontWeight: "500" },
  section: { fontSize: 13, fontWeight: "700", color: c.muted, textTransform: "uppercase", letterSpacing: 1, marginTop: 12, marginLeft: 4 },
  box: { backgroundColor: c.surface, borderRadius: 16, padding: 16, gap: 12 },
  langRow: { flexDirection: "row", gap: 8 },
  sizeRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  sizePill: { width: 36, height: 28, borderRadius: 6, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  sizePillText: { fontWeight: "800", color: c.onBrandTertiary },
}));
