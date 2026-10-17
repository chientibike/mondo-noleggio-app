import { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Image } from "expo-image";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, imageUri, CATEGORY_PRICES, type Bike, type Category, type Size } from "@/src/api";
import { Button, Chip } from "@/src/components/ui";
import { PhotoPicker } from "@/src/components/PhotoPicker";
import { CATEGORY_LABELS, SIZES, SIZE_HEIGHTS, SPEC_KEYS } from "@/src/format";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";
import { useI18n } from "@/src/i18n";

const CATS: Category[] = ["gravel", "egravel", "ebike_mtb"];

export default function BikeForm() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();
  const { t } = useI18n();

  const [name, setName] = useState("");
  const [category, setCategory] = useState<Category>("gravel");
  const [description, setDescription] = useState("");
  const [descriptionEn, setDescriptionEn] = useState("");
  const [specs, setSpecs] = useState<Record<string, string>>({});
  const [imageUrl, setImageUrl] = useState("");
  const [priceDay, setPriceDay] = useState(id ? "" : String(CATEGORY_PRICES.gravel));
  const [stock, setStock] = useState<Record<Size, number>>({ S: 0, M: 0, L: 0, XL: 0 });
  const [modelYear, setModelYear] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const existing = useQuery({ queryKey: ["bike", id], queryFn: () => api<Bike>(`/bikes/${id}`), enabled: !!id });
  useEffect(() => {
    const b = existing.data;
    if (!b) return;
    setName(b.name);
    setCategory(b.category);
    setDescription(b.description);
    setDescriptionEn(b.description_en ?? "");
    setSpecs(b.specs ?? {});
    setImageUrl(b.image_url);
    setPriceDay(String(b.price_day));
    setStock(b.stock);
    setModelYear(b.model_year ?? "");
  }, [existing.data]);

  const save = async () => {
    setError(null);
    const pd = parseFloat(priceDay.replace(",", "."));
    if (!name.trim() || !(pd > 0) || (modelYear.trim() && !/^(19|20)\d{2}$/.test(modelYear.trim()))) {
      setError(t("invalid_form"));
      return;
    }
    setBusy(true);
    try {
      const cleanSpecs = Object.fromEntries(Object.entries(specs).filter(([, v]) => v.trim()).map(([k, v]) => [k, v.trim()]));
      const body = { name: name.trim(), category, description, description_en: descriptionEn, image_url: imageUrl.trim(), price_day: pd, stock, specs: cleanSpecs, model_year: modelYear.trim() };
      await api(id ? `/admin/bikes/${id}` : "/admin/bikes", { method: id ? "PUT" : "POST", body });
      qc.invalidateQueries({ queryKey: ["bikes"] });
      qc.invalidateQueries({ queryKey: ["bike", id] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
      toast(id ? t("bike_updated") : t("bike_added"), "success");
      router.back();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const [searching, setSearching] = useState(false);
  const [source, setSource] = useState("");
  const [yearWarning, setYearWarning] = useState(false);
  const searchOnline = async () => {
    if (!name.trim()) {
      setError(t("lookup_need_name"));
      return;
    }
    setError(null);
    setSearching(true);
    try {
      const r = await api<{
        image_url: string; source_url: string; description: string; description_en: string;
        specs: Record<string, string>; year: string; year_confirmed: boolean;
      }>("/admin/bikes/lookup", {
        method: "POST",
        body: { name: name.trim(), category, year: modelYear.trim() || null, exclude_image: imageUrl.trim() || null },
      });
      if (r.image_url) setImageUrl(r.image_url);
      if (r.description) setDescription(r.description);
      if (r.description_en) setDescriptionEn(r.description_en);
      setSpecs((p) => ({ ...p, ...r.specs }));
      setSource(r.source_url);
      setYearWarning(!!r.year && !r.year_confirmed);
      if (r.year && !r.year_confirmed) toast(t("lookup_year_missing").replace("{y}", r.year), "info");
      else toast(r.image_url ? t("lookup_done") : t("lookup_no_photo"), r.image_url ? "success" : "info");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSearching(false);
    }
  };

  const step = (s: Size, d: number) => setStock((p) => ({ ...p, [s]: Math.max(0, (p[s] ?? 0) + d) }));

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="bike-form-back" onPress={() => router.back()} style={styles.back}>
          <Ionicons name="close" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{id ? t("edit_bike") : t("new_bike")}</Text>
      </View>
      <KeyboardAwareScrollView bottomOffset={100} keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 120 }]}>
        {!!imageUrl && <Image source={{ uri: imageUri(imageUrl) }} style={styles.preview} contentFit="cover" />}
        <View style={styles.lookupBox}>
          <Field label={t("model_year")}>
            <TextInput
              testID="bike-form-year"
              style={styles.input}
              value={modelYear}
              onChangeText={setModelYear}
              keyboardType="number-pad"
              maxLength={4}
              placeholder="2026"
              placeholderTextColor={colors.muted}
            />
          </Field>
          <Button
            testID="bike-form-search-online"
            title={searching ? t("lookup_searching") : t("lookup_button")}
            icon="search"
            variant="secondary"
            loading={searching}
            disabled={busy}
            onPress={searchOnline}
          />
          <Text style={styles.sizeH}>{source ? `${t("lookup_source")}: ${source}` : t("lookup_hint")}</Text>
          {yearWarning && (
            <Text style={styles.error} testID="bike-form-year-warning">
              {t("lookup_year_missing").replace("{y}", modelYear)}
            </Text>
          )}
        </View>
        <Field label={t("name")}>
          <TextInput testID="bike-form-name" style={styles.input} value={name} onChangeText={setName} placeholder={t("name_ph")} placeholderTextColor={colors.muted} />
        </Field>
        <Field label={t("category")}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {CATS.map((c) => (
              <Chip
                key={c}
                testID={`bike-form-category-${c}`}
                label={CATEGORY_LABELS[c]}
                selected={category === c}
                onPress={() => {
                  setCategory(c);
                  if (!id) setPriceDay(String(CATEGORY_PRICES[c]));
                }}
              />
            ))}
          </ScrollView>
        </Field>
        <Field label={t("price_day")}>
          <TextInput testID="bike-form-price-day" style={styles.input} value={priceDay} onChangeText={setPriceDay} keyboardType="decimal-pad" placeholder="40" placeholderTextColor={colors.muted} />
        </Field>
        <Field label={t("qty_per_size")}>
          <View style={styles.box}>
            {SIZES.map((s) => (
              <View key={s} style={styles.stockRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.sizeName}>{s}</Text>
                  <Text style={styles.sizeH}>{SIZE_HEIGHTS[s]}</Text>
                </View>
                <Pressable testID={`bike-form-stock-minus-${s}`} onPress={() => step(s, -1)} style={styles.stepBtn}>
                  <Ionicons name="remove" size={20} color={colors.onBrandSecondary} />
                </Pressable>
                <Text style={styles.stockN} testID={`bike-form-stock-${s}`}>{stock[s] ?? 0}</Text>
                <Pressable testID={`bike-form-stock-plus-${s}`} onPress={() => step(s, 1)} style={styles.stepBtn}>
                  <Ionicons name="add" size={20} color={colors.onBrandSecondary} />
                </Pressable>
              </View>
            ))}
          </View>
        </Field>
        <Field label={t("photo")}>
          <PhotoPicker onUploaded={setImageUrl} disabled={busy || searching} />
        </Field>
        <Field label={t("image_url")}>
          <TextInput testID="bike-form-image" style={styles.input} value={imageUrl} onChangeText={setImageUrl} autoCapitalize="none" placeholder="https://..." placeholderTextColor={colors.muted} />
        </Field>
        <Field label={t("description")}>
          <TextInput testID="bike-form-description" style={[styles.input, styles.multi]} value={description} onChangeText={setDescription} multiline placeholder={t("desc_ph")} placeholderTextColor={colors.muted} />
        </Field>
        <Field label={t("description_en")}>
          <TextInput testID="bike-form-description-en" style={[styles.input, styles.multi]} value={descriptionEn} onChangeText={setDescriptionEn} multiline placeholderTextColor={colors.muted} />
        </Field>
        <Field label={t("specs")}>
          <View style={styles.box}>
            {SPEC_KEYS.map((k) => (
              <View key={k} style={{ gap: 4 }}>
                <Text style={styles.sizeH}>{t(`spec_${k}`)}</Text>
                <TextInput
                  testID={`bike-form-spec-${k}`}
                  style={[styles.input, { backgroundColor: colors.surface }]}
                  value={specs[k] ?? ""}
                  onChangeText={(v) => setSpecs((p) => ({ ...p, [k]: v }))}
                  placeholderTextColor={colors.muted}
                />
              </View>
            ))}
          </View>
        </Field>
        {error && <Text style={styles.error} testID="bike-form-error">{error}</Text>}
      </KeyboardAwareScrollView>
      <KeyboardStickyView offset={{ opened: insets.bottom }} style={[styles.ctaBar, { paddingBottom: insets.bottom + 16 }]}>
        <Button testID="bike-form-save" title={id ? t("save_changes") : t("add_bike")} loading={busy} disabled={searching} onPress={save} />
      </KeyboardStickyView>
    </View>
  );
}

function Field({ label, children, style }: { label: string; children: React.ReactNode; style?: any }) {
  const styles = useStyles();
  return (
    <View style={[{ gap: 6 }, style]}>
      <Text style={styles.label}>{label}</Text>
      {children}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 12, paddingBottom: 12, borderBottomWidth: 0.5, borderBottomColor: c.border },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 20, fontWeight: "800", color: c.onSurface },
  content: { padding: 24, gap: 16 },
  preview: { height: 160, borderRadius: 16, backgroundColor: c.surfaceTertiary },
  label: { fontSize: 13, fontWeight: "700", color: c.onSurfaceSecondary },
  input: { minHeight: 52, borderRadius: 12, backgroundColor: c.surfaceSecondary, paddingHorizontal: 16, fontSize: 16, color: c.onSurface, borderWidth: 1, borderColor: c.border },
  multi: { minHeight: 100, paddingTop: 14, textAlignVertical: "top" },
  row2: { flexDirection: "row", gap: 12 },
  box: { backgroundColor: c.surfaceSecondary, borderRadius: 12, padding: 12, gap: 10 },
  stockRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  sizeName: { fontSize: 16, fontWeight: "800", color: c.onSurface },
  sizeH: { fontSize: 12, color: c.muted },
  stepBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.brandSecondary, alignItems: "center", justifyContent: "center" },
  stockN: { fontSize: 18, fontWeight: "800", color: c.onSurface, minWidth: 28, textAlign: "center" },
  error: { color: c.error, fontSize: 14, fontWeight: "600" },
  lookupBox: { gap: 6 },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: 24, paddingTop: 16, backgroundColor: c.surface, borderTopWidth: 0.5, borderTopColor: c.border },
}));
