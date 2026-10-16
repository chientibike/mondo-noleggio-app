import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, Text, TextInput, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import * as Clipboard from "expo-clipboard";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api } from "@/src/api";
import { Button } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";

export default function SheetLink() {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { t } = useI18n();
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const q = useQuery({ queryKey: ["sheet-script"], queryFn: () => api<{ script: string; url: string }>("/admin/sheet/script") });
  useEffect(() => {
    if (q.data?.url) setUrl(q.data.url);
  }, [q.data?.url]);

  const copy = async () => {
    if (!q.data) return;
    await Clipboard.setStringAsync(q.data.script);
    toast(t("code_copied"), "success");
  };

  const save = async () => {
    setError(null);
    setBusy(true);
    try {
      await api("/admin/sheet/script-url", { method: "PUT", body: { url: url.trim() } });
      qc.invalidateQueries({ queryKey: ["sheet-status"] });
      qc.invalidateQueries({ queryKey: ["sheet-script"] });
      toast(t("sheet_linked"), "success");
      router.back();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const steps = [t("step_1"), t("step_2"), t("step_3"), t("step_4"), t("step_5"), t("step_6")];

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="sheet-link-back" onPress={() => router.back()} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{t("link_sheet")}</Text>
      </View>
      <KeyboardAwareScrollView bottomOffset={24} keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 32 }]}>
        {q.data?.url ? (
          <View style={styles.okBox} testID="sheet-link-active">
            <Ionicons name="checkmark-circle" size={22} color={colors.success} />
            <Text style={styles.okText}>{t("sheet_write_on")}</Text>
          </View>
        ) : null}
        <Text style={styles.intro}>{t("link_intro")}</Text>
        {steps.map((s, i) => (
          <View key={i} style={styles.step}>
            <View style={styles.num}><Text style={styles.numText}>{i + 1}</Text></View>
            <Text style={styles.stepText}>{s}</Text>
          </View>
        ))}
        <Button testID="copy-script-button" title={t("copy_code")} icon="copy-outline" onPress={copy} disabled={!q.data} />
        <View style={styles.codeBox}>
          {q.isLoading ? <ActivityIndicator color={colors.brandPrimary} /> : (
            <Text style={styles.code} numberOfLines={8} selectable testID="script-preview">{q.data?.script}</Text>
          )}
        </View>
        <Text style={styles.label}>{t("webapp_url")}</Text>
        <TextInput
          testID="script-url-input"
          style={styles.input}
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="https://script.google.com/macros/s/.../exec"
          placeholderTextColor={colors.muted}
        />
        {error && <Text style={styles.error} testID="sheet-link-error">{error}</Text>}
        <Button testID="save-script-url-button" title={t("link_sheet")} icon="link-outline" loading={busy} disabled={url.trim().length < 10} onPress={save} />
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 12, paddingBottom: 12, borderBottomWidth: 0.5, borderBottomColor: c.border },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  content: { padding: 24, gap: 14 },
  okBox: { flexDirection: "row", gap: 8, alignItems: "center", padding: 12, borderRadius: 12, backgroundColor: c.brandTertiary },
  okText: { flex: 1, fontSize: 14, fontWeight: "600", color: c.onBrandTertiary },
  intro: { fontSize: 15, lineHeight: 22, color: c.onSurfaceSecondary },
  step: { flexDirection: "row", gap: 12, alignItems: "flex-start" },
  num: { width: 26, height: 26, borderRadius: 13, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  numText: { color: c.onBrandPrimary, fontWeight: "800", fontSize: 13 },
  stepText: { flex: 1, fontSize: 14, lineHeight: 20, color: c.onSurface },
  codeBox: { backgroundColor: c.surfaceSecondary, borderRadius: 12, padding: 12, minHeight: 60 },
  code: { fontFamily: "monospace", fontSize: 11, color: c.onSurfaceTertiary },
  label: { fontSize: 13, fontWeight: "700", color: c.onSurfaceSecondary, marginTop: 8 },
  input: { height: 52, borderRadius: 12, backgroundColor: c.surfaceSecondary, paddingHorizontal: 16, fontSize: 14, color: c.onSurface, borderWidth: 1, borderColor: c.border },
  error: { color: c.error, fontSize: 14, fontWeight: "600" },
}));
