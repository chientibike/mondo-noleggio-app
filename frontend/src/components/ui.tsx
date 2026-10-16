import React from "react";
import { ActivityIndicator, Pressable, Text, View, type ViewStyle } from "react-native";
import * as Haptics from "expo-haptics";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { makeStyles, useTheme } from "@/src/theme";

type BtnProps = {
  title: string;
  onPress: () => void;
  testID: string;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  loading?: boolean;
  disabled?: boolean;
  icon?: React.ComponentProps<typeof Ionicons>["name"];
  style?: ViewStyle;
};

export function Button({ title, onPress, testID, variant = "primary", loading, disabled, icon, style }: BtnProps) {
  const styles = useStyles();
  const { colors } = useTheme();
  const bg = {
    primary: colors.brandPrimary,
    secondary: colors.brandSecondary,
    danger: colors.error,
    ghost: "transparent",
  }[variant];
  const fg = {
    primary: colors.onBrandPrimary,
    secondary: colors.onBrandSecondary,
    danger: colors.onError,
    ghost: colors.brandPrimary,
  }[variant];
  return (
    <Pressable
      testID={testID}
      disabled={disabled || loading}
      onPress={() => {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
        onPress();
      }}
      style={({ pressed }) => [
        styles.btn,
        { backgroundColor: bg, opacity: disabled ? 0.45 : pressed ? 0.85 : 1, transform: [{ scale: pressed ? 0.98 : 1 }] },
        variant === "ghost" && styles.ghost,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <View style={styles.row}>
          {icon && <Ionicons name={icon} size={18} color={fg} />}
          <Text style={[styles.btnText, { color: fg }]}>{title}</Text>
        </View>
      )}
    </Pressable>
  );
}

export function Chip({
  label,
  sub,
  selected,
  onPress,
  testID,
  disabled,
}: {
  label: string;
  sub?: string;
  selected: boolean;
  onPress: () => void;
  testID: string;
  disabled?: boolean;
}) {
  const styles = useStyles();
  return (
    <Pressable
      testID={testID}
      disabled={disabled}
      onPress={() => {
        Haptics.selectionAsync().catch(() => {});
        onPress();
      }}
      style={({ pressed }) => [
        styles.chip,
        sub ? styles.chipTall : null,
        selected ? styles.chipOn : styles.chipOff,
        disabled && styles.chipDisabled,
        pressed && { opacity: 0.8 },
      ]}
    >
      <Text style={[styles.chipText, selected && styles.chipTextOn, disabled && styles.chipTextDisabled]}>{label}</Text>
      {sub ? <Text style={[styles.chipSub, selected && styles.chipTextOn]}>{sub}</Text> : null}
    </Pressable>
  );
}

export function Badge({ label, tone }: { label: string; tone: "success" | "warning" | "error" | "neutral" | "brand" }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const map = {
    success: [colors.success, colors.onSuccess],
    warning: [colors.warning, colors.onWarning],
    error: [colors.error, colors.onError],
    neutral: [colors.surfaceTertiary, colors.onSurfaceTertiary],
    brand: [colors.brandSecondary, colors.onBrandSecondary],
  }[tone];
  return (
    <View style={[styles.badge, { backgroundColor: map[0] }]}>
      <Text style={[styles.badgeText, { color: map[1] }]}>{label}</Text>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  btn: { minHeight: 52, borderRadius: 12, alignItems: "center", justifyContent: "center", paddingHorizontal: 20 },
  ghost: { borderWidth: 1, borderColor: c.borderStrong },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  btnText: { fontSize: 16, fontWeight: "700" },
  chip: {
    height: 36,
    paddingHorizontal: 14,
    borderRadius: 999,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    flexShrink: 0,
  },
  chipTall: { height: 56, borderRadius: 12, minWidth: 64 },
  chipOn: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipOff: { backgroundColor: c.surface, borderColor: c.border },
  chipDisabled: { backgroundColor: c.surfaceSecondary, borderColor: c.surfaceSecondary },
  chipText: { fontSize: 14, fontWeight: "600", color: c.onSurface },
  chipTextOn: { color: c.onBrandPrimary },
  chipTextDisabled: { color: c.muted, textDecorationLine: "line-through" },
  chipSub: { fontSize: 11, color: c.muted, marginTop: 2 },
  badge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6, alignSelf: "flex-start" },
  badgeText: { fontSize: 12, fontWeight: "700" },
}));
