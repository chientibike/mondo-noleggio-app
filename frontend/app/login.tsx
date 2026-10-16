import { useEffect, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { useAuth } from "@/src/auth";
import { Button } from "@/src/components/ui";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";

export default function Login() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const { user, login, register, loginWithGoogle } = useAuth();
  const { t } = useI18n();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [gBusy, setGBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Once authenticated, leave the login screen.
  useEffect(() => {
    if (user) {
      if (router.canGoBack()) router.back();
      else router.replace("/");
    }
  }, [user, router]);

  const submit = async () => {
    setError(null);
    if (!email.trim() || !password || (mode === "register" && !name.trim())) {
      setError(t("fill_all"));
      return;
    }
    setBusy(true);
    try {
      if (mode === "login") await login(email, password);
      else await register(name, email, password);
      toast(mode === "login" ? t("welcome_back") : t("account_created"), "success");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const google = async () => {
    setError(null);
    setGBusy(true);
    try {
      await loginWithGoogle();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGBusy(false);
    }
  };

  return (
    <View style={styles.root}>
      <KeyboardAwareScrollView
        bottomOffset={24}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={[styles.content, { paddingTop: insets.top + 16, paddingBottom: insets.bottom + 24 }]}
      >
        <Pressable testID="login-close-button" onPress={() => (router.canGoBack() ? router.back() : router.replace("/"))} style={styles.close}>
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={styles.logo}>
          <Ionicons name="bicycle" size={36} color={colors.onBrandPrimary} />
        </View>
        <Text style={styles.title}>{mode === "login" ? t("login") : t("register_title")}</Text>
        <Text style={styles.sub}>{t("login_sub")}</Text>

        <Button testID="google-login-button" title={t("google")} icon="logo-google" variant="ghost" loading={gBusy} onPress={google} />

        <View style={styles.orRow}>
          <View style={styles.line} />
          <Text style={styles.or}>{t("or")}</Text>
          <View style={styles.line} />
        </View>

        {mode === "register" && (
          <View style={styles.field}>
            <Text style={styles.label}>{t("name")}</Text>
            <TextInput testID="register-name-input" style={styles.input} value={name} onChangeText={setName} placeholder="Mario Rossi" placeholderTextColor={colors.muted} />
          </View>
        )}
        <View style={styles.field}>
          <Text style={styles.label}>{t("email")}</Text>
          <TextInput
            testID="login-email-input"
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
            placeholder="nome@email.it"
            placeholderTextColor={colors.muted}
          />
        </View>
        <View style={styles.field}>
          <Text style={styles.label}>{t("password")}</Text>
          <TextInput
            testID="login-password-input"
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholder={mode === "register" ? t("pw_ph_register") : t("pw_ph_login")}
            placeholderTextColor={colors.muted}
            onSubmitEditing={submit}
          />
        </View>

        {error && <Text style={styles.error} testID="login-error">{error}</Text>}

        <Button testID="login-submit-button" title={mode === "login" ? t("login") : t("register")} loading={busy} onPress={submit} />

        <Pressable testID="toggle-auth-mode" onPress={() => { setMode(mode === "login" ? "register" : "login"); setError(null); }} style={styles.toggle}>
          <Text style={styles.toggleText}>
            {mode === "login" ? t("no_account") : t("have_account")}
            <Text style={styles.toggleLink}>{mode === "login" ? t("register") : t("login")}</Text>
          </Text>
        </Pressable>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  content: { paddingHorizontal: 24, gap: 16 },
  close: { alignSelf: "flex-end", width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  logo: { width: 64, height: 64, borderRadius: 20, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 30, fontWeight: "800", color: c.onSurface, letterSpacing: -0.5 },
  sub: { fontSize: 15, color: c.onSurfaceTertiary, marginTop: -8, marginBottom: 8 },
  orRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  line: { flex: 1, height: 0.5, backgroundColor: c.divider },
  or: { color: c.muted, fontSize: 13 },
  field: { gap: 6 },
  label: { fontSize: 13, fontWeight: "700", color: c.onSurfaceSecondary },
  input: { height: 52, borderRadius: 12, backgroundColor: c.surfaceSecondary, paddingHorizontal: 16, fontSize: 16, color: c.onSurface, borderWidth: 1, borderColor: c.border },
  error: { color: c.error, fontSize: 14, fontWeight: "600" },
  toggle: { alignItems: "center", paddingVertical: 12 },
  toggleText: { color: c.onSurfaceTertiary, fontSize: 14 },
  toggleLink: { color: c.brandPrimary, fontWeight: "700" },
}));
