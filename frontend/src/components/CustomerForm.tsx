import { useState } from "react";
import { Text, TextInput, View } from "react-native";
import { Image } from "expo-image";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { PhotoPicker } from "@/src/components/PhotoPicker";

import { Chip } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { makeStyles, useTheme } from "@/src/theme";

export type Customer = {
  full_name: string;
  tax_code: string;
  birth_date: string; // YYYY-MM-DD (sent) — typed as DD/MM/YYYY
  address: string;
  city_zip: string;
  nationality: string;
  doc_type: "ci" | "patente" | "passaporto" | "";
  doc_number: string;
  doc_issuer_expiry: string;
  emergency_contact: string;
  doc_front_id: string;
  doc_back_id: string;
};

export const EMPTY_CUSTOMER: Customer = {
  full_name: "", tax_code: "", birth_date: "", address: "", city_zip: "", nationality: "Italiana",
  doc_type: "", doc_number: "", doc_issuer_expiry: "", emergency_contact: "",
  doc_front_id: "", doc_back_id: "",
};

/** "31/12/1980" -> "1980-12-31" (or "" if not a real date) */
export function toIsoDate(v: string): string {
  const m = v.trim().match(/^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$/);
  if (!m) return "";
  const [d, mo, y] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const dt = new Date(Date.UTC(y, mo - 1, d));
  if (dt.getUTCDate() !== d || dt.getUTCMonth() !== mo - 1 || y < 1900 || dt > new Date()) return "";
  return `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

export function fromIsoDate(v: string): string {
  const m = v.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return m ? `${m[3]}/${m[2]}/${m[1]}` : v;
}

/** Returns the list of invalid field keys (empty = ok). */
export function customerErrors(c: Customer): (keyof Customer)[] {
  const bad: (keyof Customer)[] = [];
  if (c.full_name.trim().length < 3) bad.push("full_name");
  if (!/^[A-Za-z0-9]{11,20}$/.test(c.tax_code.trim())) bad.push("tax_code");
  if (!toIsoDate(c.birth_date)) bad.push("birth_date");
  if (c.address.trim().length < 3) bad.push("address");
  if (c.city_zip.trim().length < 3) bad.push("city_zip");
  if (c.nationality.trim().length < 2) bad.push("nationality");
  if (!c.doc_type) bad.push("doc_type");
  if (c.doc_number.trim().length < 4) bad.push("doc_number");
  if (c.doc_issuer_expiry.trim().length < 3) bad.push("doc_issuer_expiry");
  if (!c.doc_front_id) bad.push("doc_front_id");
  if (!c.doc_back_id) bad.push("doc_back_id");
  return bad;
}

const FIELDS: { key: keyof Customer; ph?: string; caps?: "characters" | "words" | "none"; kb?: "numbers-and-punctuation" }[] = [
  { key: "full_name", caps: "words" },
  { key: "tax_code", caps: "characters", ph: "RSSMRA80A01L191X" },
  { key: "birth_date", ph: "GG/MM/AAAA", kb: "numbers-and-punctuation" },
  { key: "address", caps: "words" },
  { key: "city_zip", caps: "words", ph: "Tolentino 62029" },
  { key: "nationality", caps: "words" },
];
const DOC_FIELDS: { key: keyof Customer; ph?: string; caps?: "characters" | "words" }[] = [
  { key: "doc_number", caps: "characters" },
  { key: "doc_issuer_expiry", ph: "Comune di Tolentino, 31/12/2030" },
  { key: "emergency_contact", caps: "words" },
];

export function CustomerForm({ value, onChange, showErrors }: { value: Customer; onChange: (c: Customer) => void; showErrors: boolean }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const bad = showErrors ? customerErrors(value) : [];
  const set = (k: keyof Customer, v: string) => onChange({ ...value, [k]: k === "tax_code" ? v.toUpperCase() : v });

  const input = (f: { key: keyof Customer; ph?: string; caps?: any; kb?: any }) => (
    <View key={f.key} style={{ gap: 4 }}>
      <Text style={styles.label}>{t(`cust_${f.key}` as "cust_full_name")}</Text>
      <TextInput
        testID={`customer-${f.key}`}
        style={[styles.input, bad.includes(f.key) && styles.inputBad]}
        value={value[f.key]}
        onChangeText={(v) => set(f.key, v)}
        autoCapitalize={f.caps ?? "sentences"}
        keyboardType={f.kb ?? "default"}
        placeholder={f.ph}
        placeholderTextColor={colors.muted}
      />
    </View>
  );

  return (
    <View style={styles.box} testID="customer-form">
      <Text style={styles.hint}>{t("cust_hint")}</Text>
      {FIELDS.map(input)}
      <Text style={styles.label}>{t("cust_doc_type")}</Text>
      <View style={[styles.chips, bad.includes("doc_type") && styles.chipsBad]}>
        {(["ci", "patente", "passaporto"] as const).map((d) => (
          <Chip key={d} testID={`customer-doc-${d}`} label={t(`doc_${d}`)} selected={value.doc_type === d} onPress={() => set("doc_type", d)} />
        ))}
      </View>
      {DOC_FIELDS.map(input)}
      {(["doc_front_id", "doc_back_id"] as const).map((k) => (
        <DocPhoto key={k} side={k} id={value[k]} bad={bad.includes(k)} onUploaded={(id) => set(k, id)} />
      ))}
      {bad.length > 0 && <Text style={styles.err} testID="customer-form-error">{t("cust_invalid")}</Text>}
    </View>
  );
}

function DocPhoto({ side, id, bad, onUploaded }: { side: "doc_front_id" | "doc_back_id"; id: string; bad: boolean; onUploaded: (id: string) => void }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const { t } = useI18n();
  const [preview, setPreview] = useState<string | null>(null);
  const prefix = side === "doc_front_id" ? "customer-doc-front" : "customer-doc-back";
  return (
    <View style={[styles.docBox, bad && styles.chipsBad]} testID={`${prefix}-box`}>
      <View style={styles.docHead}>
        {preview ? (
          <Image source={{ uri: preview }} style={styles.docThumb} contentFit="cover" />
        ) : (
          <View style={[styles.docThumb, styles.docEmpty]}>
            <Ionicons name={id ? "checkmark-circle" : "card-outline"} size={26} color={id ? colors.brandPrimary : colors.muted} />
          </View>
        )}
        <View style={{ flex: 1 }}>
          <Text style={styles.label}>{t(side === "doc_front_id" ? "doc_front" : "doc_back")}</Text>
          <Text style={styles.hint} testID={`${prefix}-status`}>{id ? t("doc_photo_ok") : t("doc_photo_missing")}</Text>
        </View>
      </View>
      <PhotoPicker
        uploadPath="/me/id-document"
        testIDPrefix={prefix}
        aspect={[16, 10]}
        successKey="doc_uploaded"
        onUploaded={(d, uri) => {
          setPreview(uri);
          onUploaded(d.id);
        }}
      />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  docBox: { gap: 8, borderRadius: 12, borderWidth: 1, borderColor: c.border, padding: 10 },
  docHead: { flexDirection: "row", alignItems: "center", gap: 12 },
  docThumb: { width: 72, height: 46, borderRadius: 8, backgroundColor: c.surfaceSecondary },
  docEmpty: { alignItems: "center", justifyContent: "center" },
  box: { backgroundColor: c.surface, borderRadius: 16, padding: 16, gap: 10 },
  hint: { fontSize: 13, color: c.onSurfaceTertiary },
  label: { fontSize: 12, fontWeight: "700", color: c.onSurfaceSecondary },
  input: { minHeight: 48, borderRadius: 12, backgroundColor: c.surfaceSecondary, paddingHorizontal: 14, fontSize: 15, color: c.onSurface, borderWidth: 1, borderColor: c.border },
  inputBad: { borderColor: c.error },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8, borderRadius: 12, borderWidth: 1, borderColor: "transparent", padding: 2 },
  chipsBad: { borderColor: c.error },
  err: { color: c.error, fontSize: 13, fontWeight: "600" },
}));
