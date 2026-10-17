import { useState } from "react";
import { Alert, Linking, Platform, View } from "react-native";
import * as ImagePicker from "expo-image-picker";

import { BACKEND_URL, getToken } from "@/src/api";
import { Button } from "@/src/components/ui";
import { useI18n } from "@/src/i18n";
import { useToast } from "@/src/toast";
import { uploadForm } from "@/src/utils/upload";

type Source = "camera" | "library";

/** Explain why, ask (max twice), and send to Settings when permanently denied. Never blocks the rest of the form. */
async function ensurePermission(source: Source, t: ReturnType<typeof useI18n>["t"]): Promise<boolean> {
  if (Platform.OS === "web") return true;
  const get = source === "camera" ? ImagePicker.getCameraPermissionsAsync : ImagePicker.getMediaLibraryPermissionsAsync;
  const request = source === "camera" ? ImagePicker.requestCameraPermissionsAsync : ImagePicker.requestMediaLibraryPermissionsAsync;
  const current = await get();
  if (current.granted) return true;
  const title = t(source === "camera" ? "perm_camera_title" : "perm_library_title");
  if (!current.canAskAgain) {
    Alert.alert(title, t("perm_blocked"), [
      { text: t("cancel"), style: "cancel" },
      { text: t("open_settings"), onPress: () => Linking.openSettings() },
    ]);
    return false;
  }
  const ok = await new Promise<boolean>((resolve) =>
    Alert.alert(title, t(source === "camera" ? "perm_camera_why" : "perm_library_why"), [
      { text: t("cancel"), style: "cancel", onPress: () => resolve(false) },
      { text: t("continue"), onPress: () => resolve(true) },
    ]),
  );
  if (!ok) return false;
  const res = await request();
  if (res.granted) return true;
  if (!res.canAskAgain) {
    Alert.alert(title, t("perm_blocked"), [
      { text: t("cancel"), style: "cancel" },
      { text: t("open_settings"), onPress: () => Linking.openSettings() },
    ]);
  }
  return false;
}

type Props = {
  onUploaded: (data: any, localUri: string) => void;
  disabled?: boolean;
  uploadPath?: string; // backend route under /api
  testIDPrefix?: string;
  aspect?: [number, number];
  successKey?: "photo_uploaded" | "doc_uploaded";
};

export function PhotoPicker({
  onUploaded, disabled, uploadPath = "/admin/upload", testIDPrefix = "bike-form-photo", aspect = [3, 2], successKey = "photo_uploaded",
}: Props) {
  const { t } = useI18n();
  const toast = useToast();
  const [busy, setBusy] = useState<Source | null>(null);

  const pick = async (source: Source) => {
    if (!(await ensurePermission(source, t))) return;
    const opts: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 0.7, allowsEditing: true, aspect };
    const result = source === "camera" ? await ImagePicker.launchCameraAsync(opts) : await ImagePicker.launchImageLibraryAsync(opts);
    if (result.canceled || !result.assets?.[0]) return;
    const asset = result.assets[0];
    setBusy(source);
    try {
      const res = await uploadForm(`${BACKEND_URL}/api${uploadPath}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
        files: { file: { uri: asset.uri, name: asset.fileName ?? "bike.jpg", mimeType: asset.mimeType ?? "image/jpeg" } },
      });
      const text = await res.text();
      const data = text ? JSON.parse(text) : null;
      if (!res.ok) throw new Error(typeof data?.detail === "string" ? data.detail : t("upload_failed"));
      onUploaded(data, asset.uri);
      toast(t(successKey), "success");
    } catch (e: any) {
      toast(e.message || t("upload_failed"), "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <View style={{ flexDirection: "row", gap: 8 }}>
      <View style={{ flex: 1 }}>
        <Button testID={`${testIDPrefix}-camera`} title={t("take_photo")} icon="camera" variant="secondary"
          loading={busy === "camera"} disabled={disabled || !!busy} onPress={() => pick("camera")} />
      </View>
      <View style={{ flex: 1 }}>
        <Button testID={`${testIDPrefix}-library`} title={t("from_gallery")} icon="images" variant="secondary"
          loading={busy === "library"} disabled={disabled || !!busy} onPress={() => pick("library")} />
      </View>
    </View>
  );
}
