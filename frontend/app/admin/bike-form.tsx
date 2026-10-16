import { useEffect, useState } from "react";
import { Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Image } from "expo-image";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { api, type Bike, type Category, type Size } from "@/src/api";
import { Button, Chip } from "@/src/components/ui";
import { CATEGORY_LABELS, SIZES, SIZE_HEIGHTS } from "@/src/format";
import { useToast } from "@/src/toast";
import { makeStyles, useTheme } from "@/src/theme";

const CATS: Category[] = ["gravel", "ebike", "gravel_muscolare"];

export default function BikeForm() {
  const { id } = useLocalSearchParams<{ id?: string }>();
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();
  const router = useRouter();
  const toast = useToast();
  const qc = useQueryClient();

  const [name, setName] = useState("");
  const [category, setCategory] = useState<Category>("gravel");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [priceHour, setPriceHour] = useState("");
  const [priceDay, setPriceDay] = useState("");
  const [stock, setStock] = useState<Record<Size, number>>({ S: 0, M: 0, L: 0, XL: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const existing = useQuery({ queryKey: ["bike", id], queryFn: () => api<Bike>(`/bikes/${id}`), enabled: !!id });
  useEffect(() => {
    const b = existing.data;
    if (!b) return;
    setName(b.name);
    setCategory(b.category);
    setDescription(b.description);
    setImageUrl(b.image_url);
    setPriceHour(String(b.price_hour));
    setPriceDay(String(b.price_day));
    setStock(b.stock);
  }, [existing.data]);

  const save = async () => {
    setError(null);
    const ph = parseFloat(priceHour.replace(",", "."));
    const pd = parseFloat(priceDay.replace(",", "."));
    if (!name.trim() || !(ph > 0) || !(pd > 0)) {
      setError("Inserisci nome e prezzi validi");
      return;
    }
    setBusy(true);
    try {
      const body = { name: name.trim(), category, description, image_url: imageUrl.trim(), price_hour: ph, price_day: pd, stock };
      await api(id ? `/admin/bikes/${id}` : "/admin/bikes", { method: id ? "PUT" : "POST", body });
      qc.invalidateQueries({ queryKey: ["bikes"] });
      qc.invalidateQueries({ queryKey: ["bike", id] });
      qc.invalidateQueries({ queryKey: ["admin-stats"] });
      toast(id ? "Bici aggiornata" : "Bici aggiunta", "success");
      router.back();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const step = (s: Size, d: number) => setStock((p) => ({ ...p, [s]: Math.max(0, (p[s] ?? 0) + d) }));

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
        <Pressable testID="bike-form-back" onPress={() => router.back()} style={styles.back}>
          <Ionicons name="close" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>{id ? "Modifica bici" : "Nuova bici"}</Text>
      </View>
      <KeyboardAwareScrollView bottomOffset={100} keyboardShouldPersistTaps="handled" contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 120 }]}>
        {!!imageUrl && <Image source={{ uri: imageUrl }} style={styles.preview} contentFit="cover" />}
        <Field label="Nome">
          <TextInput testID="bike-form-name" style={styles.input} value={name} onChangeText={setName} placeholder="Es. Bianchi Arcadex" placeholderTextColor={colors.muted} />
        </Field>
        <Field label="Categoria">
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
            {CATS.map((c) => (
              <Chip key={c} testID={`bike-form-category-${c}`} label={CATEGORY_LABELS[c]} selected={category === c} onPress={() => setCategory(c)} />
            ))}
          </ScrollView>
        </Field>
        <View style={styles.row2}>
          <Field label="Prezzo €/ora" style={{ flex: 1 }}>
            <TextInput testID="bike-form-price-hour" style={styles.input} value={priceHour} onChangeText={setPriceHour} keyboardType="decimal-pad" placeholder="8" placeholderTextColor={colors.muted} />
          </Field>
          <Field label="Prezzo €/giorno" style={{ flex: 1 }}>
            <TextInput testID="bike-form-price-day" style={styles.input} value={priceDay} onChangeText={setPriceDay} keyboardType="decimal-pad" placeholder="35" placeholderTextColor={colors.muted} />
          </Field>
        </View>
        <Field label="Quantità per taglia">
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
        <Field label="URL immagine">
          <TextInput testID="bike-form-image" style={styles.input} value={imageUrl} onChangeText={setImageUrl} autoCapitalize="none" placeholder="https://..." placeholderTextColor={colors.muted} />
        </Field>
        <Field label="Descrizione">
          <TextInput testID="bike-form-description" style={[styles.input, styles.multi]} value={description} onChangeText={setDescription} multiline placeholder="Caratteristiche, cambio, autonomia..." placeholderTextColor={colors.muted} />
        </Field>
        {error && <Text style={styles.error} testID="bike-form-error">{error}</Text>}
      </KeyboardAwareScrollView>
      <KeyboardStickyView offset={{ opened: insets.bottom }} style={[styles.ctaBar, { paddingBottom: insets.bottom + 16 }]}>
        <Button testID="bike-form-save" title={id ? "Salva modifiche" : "Aggiungi bici"} loading={busy} onPress={save} />
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
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: 24, paddingTop: 16, backgroundColor: c.surface, borderTopWidth: 0.5, borderTopColor: c.border },
}));
