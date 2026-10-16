import { Tabs } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { Platform } from "react-native";
import * as Haptics from "expo-haptics";
import { Ionicons } from "@react-native-vector-icons/ionicons";

import { usesNativeTabs } from "@/src/navigation";
import { useI18n } from "@/src/i18n";
import { useTheme } from "@/src/theme";

export default function TabsLayout() {
  const { colors } = useTheme();
  const { t } = useI18n();

  if (usesNativeTabs) {
    return (
      <NativeTabs tintColor={colors.brandPrimary}>
        <NativeTabs.Trigger name="index">
          <NativeTabs.Trigger.Icon sf="bicycle" />
          <NativeTabs.Trigger.Label>{t("tab_bikes")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="bookings">
          <NativeTabs.Trigger.Icon sf="calendar" />
          <NativeTabs.Trigger.Label>{t("tab_bookings")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
        <NativeTabs.Trigger name="profile">
          <NativeTabs.Trigger.Icon sf="person.crop.circle" />
          <NativeTabs.Trigger.Label>{t("tab_profile")}</NativeTabs.Trigger.Label>
        </NativeTabs.Trigger>
      </NativeTabs>
    );
  }

  return (
    <Tabs
      screenListeners={{ tabPress: () => Haptics.selectionAsync().catch(() => {}) }}
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.brandPrimary,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: {
          backgroundColor: colors.surface,
          borderTopColor: colors.border,
          ...(Platform.OS === "web" ? { height: 64 } : {}),
        },
        tabBarItemStyle: { alignSelf: "center" },
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: t("tab_bikes"),
          tabBarButtonTestID: "tab-bikes",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons name={focused ? "bicycle" : "bicycle-outline"} color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="bookings"
        options={{
          title: t("tab_bookings"),
          tabBarButtonTestID: "tab-bookings",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons name={focused ? "calendar" : "calendar-outline"} color={color} size={size} />
          ),
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: t("tab_profile"),
          tabBarButtonTestID: "tab-profile",
          tabBarIcon: ({ color, focused, size }) => (
            <Ionicons name={focused ? "person-circle" : "person-circle-outline"} color={color} size={size} />
          ),
        }}
      />
    </Tabs>
  );
}
