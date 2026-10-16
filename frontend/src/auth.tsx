import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Platform } from "react-native";
import * as Linking from "expo-linking";
import * as WebBrowser from "expo-web-browser";

import { api, loadToken, persistToken, setUnauthorizedHandler, type User } from "./api";

WebBrowser.maybeCompleteAuthSession();

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  loginWithGoogle: () => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>(null as any);

function extractSessionId(url: string | null | undefined) {
  if (!url) return null;
  const m = url.match(/[?#&]session_id=([^&#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const sent = useRef(new Set<string>());

  const exchange = useCallback(async (sessionId: string) => {
    if (sent.current.has(sessionId)) return false;
    sent.current.add(sessionId);
    const res = await api<{ session_token: string; user: User }>("/auth/session", {
      method: "POST",
      body: { session_id: sessionId },
    });
    await persistToken(res.session_token);
    setUser(res.user);
    return true;
  }, []);

  const logout = useCallback(async () => {
    await persistToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      persistToken(null);
      setUser(null);
    });
    (async () => {
      try {
        if (Platform.OS === "web" && typeof window !== "undefined") {
          const sid = extractSessionId(window.location.href);
          if (sid) {
            try {
              await exchange(sid);
              const url = new URL(window.location.href);
              url.searchParams.delete("session_id");
              url.hash = url.hash.replace(/[#&]?session_id=[^&#]+/, "");
              window.history.replaceState(window.history.state, "", url.toString());
              return;
            } catch {
              // fall through to stored session
            }
          }
        } else {
          const sid = extractSessionId(await Linking.getInitialURL());
          if (sid) {
            try {
              if (await exchange(sid)) return;
            } catch {}
          }
        }
        const token = await loadToken();
        if (token) {
          try {
            setUser(await api<User>("/auth/me"));
          } catch {
            await persistToken(null);
            setUser(null);
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [exchange]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api<{ token: string; user: User }>("/auth/login", { method: "POST", body: { email, password } });
    await persistToken(res.token);
    setUser(res.user);
  }, []);

  const register = useCallback(async (name: string, email: string, password: string) => {
    const res = await api<{ token: string; user: User }>("/auth/register", {
      method: "POST",
      body: { name, email, password },
    });
    await persistToken(res.token);
    setUser(res.user);
  }, []);

  const loginWithGoogle = useCallback(async () => {
    if (Platform.OS === "web") {
      const redirect = window.location.origin + "/";
      window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirect)}`;
      return;
    }
    const redirect = Linking.createURL("");
    let captured: string | null = null;
    const sub = Linking.addEventListener("url", ({ url }) => {
      if (extractSessionId(url)) captured = url;
    });
    try {
      const result = await WebBrowser.openAuthSessionAsync(
        `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirect)}`,
        redirect,
      );
      const url = (result.type === "success" ? result.url : null) ?? captured ?? (await Linking.getInitialURL());
      const sid = extractSessionId(url);
      if (sid) await exchange(sid);
      else if (result.type !== "success") throw new Error("Accesso con Google annullato");
    } finally {
      sub.remove();
    }
  }, [exchange]);

  return (
    <Ctx.Provider value={{ user, loading, login, register, loginWithGoogle, logout }}>{children}</Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
