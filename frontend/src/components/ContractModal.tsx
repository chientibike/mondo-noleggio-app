import { useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, Text, View } from "react-native";
import { useQuery } from "@tanstack/react-query";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api } from "@/src/api";
import { Button } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

export type Contract = { version: string; lines: string[] };
type Consent = "contract" | "clauses" | "privacy";
const CONSENTS: Consent[] = ["contract", "clauses", "privacy"];

export function useContract() {
  return useQuery({ queryKey: ["contract"], queryFn: () => api<Contract>("/contract"), staleTime: 5 * 60_000 });
}

const isHeading = (l: string) => /^\d+\.\s/.test(l) || /^[A-ZÀ-Ü0-9 &'’,.()\-—"/]{12,}:?$/.test(l);

/** Full-screen contract: read it, tick the three consents, accept. */
export function ContractModal({ visible, contract, onClose, onAccept }: {
  visible: boolean; contract?: Contract; onClose: () => void; onAccept: () => void;
}) {
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const [checked, setChecked] = useState<Record<Consent, boolean>>({ contract: false, clauses: false, privacy: false });
  const all = CONSENTS.every((k) => checked[k]);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.root, { paddingTop: insets.top || 12 }]}>
        <View style={styles.header}>
          <Text style={styles.title}>{t("contract_title")}</Text>
          <Pressable testID="contract-close" onPress={onClose} style={styles.close} accessibilityLabel={t("cancel")}>
            <Ionicons name="close" size={24} color={colors.onSurface} />
          </Pressable>
        </View>
        {!contract ? (
          <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
        ) : (
          <ScrollView testID="contract-text" contentContainerStyle={styles.body}>
            {contract.lines.map((l, i) => (
              <Text key={i} style={i === 0 ? styles.docTitle : isHeading(l) ? styles.heading : styles.line}>{l}</Text>
            ))}
          </ScrollView>
        )}
        <View style={[styles.footer, { paddingBottom: insets.bottom + 16 }]}>
          {CONSENTS.map((k) => (
            <Pressable
              key={k}
              testID={`contract-consent-${k}`}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: checked[k] }}
              onPress={() => setChecked((p) => ({ ...p, [k]: !p[k] }))}
              style={styles.consent}
            >
              <Ionicons name={checked[k] ? "checkbox" : "square-outline"} size={24} color={checked[k] ? colors.brandPrimary : colors.borderStrong} />
              <Text style={styles.consentText}>{t(`consent_${k}`)}</Text>
            </Pressable>
          ))}
          <Button testID="contract-accept" title={t("contract_accept")} disabled={!all || !contract} onPress={onAccept} />
        </View>
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingBottom: 8, borderBottomWidth: 0.5, borderBottomColor: c.border },
  title: { flex: 1, fontSize: 18, fontWeight: "800", color: c.onSurface },
  close: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  body: { padding: 16, gap: 8 },
  docTitle: { fontSize: 16, fontWeight: "800", color: c.onSurface },
  heading: { fontSize: 14, fontWeight: "800", color: c.onSurface, marginTop: 8 },
  line: { fontSize: 13, lineHeight: 19, color: c.onSurfaceSecondary },
  footer: { paddingHorizontal: 16, paddingTop: 12, gap: 10, borderTopWidth: 0.5, borderTopColor: c.border, backgroundColor: c.surface },
  consent: { flexDirection: "row", gap: 10, alignItems: "flex-start", minHeight: 44 },
  consentText: { flex: 1, fontSize: 13, lineHeight: 18, color: c.onSurface },
}));
