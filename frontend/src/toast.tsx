import React, { createContext, useCallback, useContext, useRef, useState } from "react";
import { Text, View } from "react-native";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { makeStyles, useTheme } from "@/src/theme";

type ToastType = "success" | "error" | "info";
type ToastState = { id: number; msg: string; type: ToastType } | null;

const ToastCtx = createContext<(msg: string, type?: ToastType) => void>(() => {});

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toast, setToast] = useState<ToastState>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();

  const show = useCallback((msg: string, type: ToastType = "info") => {
    if (timer.current) clearTimeout(timer.current);
    setToast({ id: Date.now(), msg, type });
    timer.current = setTimeout(() => setToast(null), 3000);
  }, []);

  const bg = toast?.type === "error" ? colors.error : toast?.type === "success" ? colors.brandPrimary : colors.surfaceInverse;
  const icon = toast?.type === "error" ? "alert-circle" : toast?.type === "success" ? "checkmark-circle" : "information-circle";

  return (
    <ToastCtx.Provider value={show}>
      {children}
      {toast && (
        <Animated.View
          key={toast.id}
          entering={FadeInUp}
          exiting={FadeOutUp}
          style={[styles.wrap, { top: insets.top + 8, pointerEvents: "none" }]}
        >
          <View testID="toast-message" style={[styles.toast, { backgroundColor: bg }]}>
            <Ionicons name={icon} size={20} color={colors.onSurfaceInverse} />
            <Text style={styles.text}>{toast.msg}</Text>
          </View>
        </Animated.View>
      )}
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

const useStyles = makeStyles((c) => ({
  wrap: { position: "absolute", left: 16, right: 16, zIndex: 1000, alignItems: "center" },
  toast: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
    maxWidth: 520,
    width: "100%",
    shadowColor: "#000",
    shadowOpacity: 0.15,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  text: { color: c.onSurfaceInverse, fontSize: 14, fontWeight: "600", flex: 1 },
}));
