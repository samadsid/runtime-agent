import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import type { StaffIdentity } from "@/api/contracts";
import { StaffApiError } from "@/api/errors";
import { apiClient, staffApi } from "@/app-services";
import { recordEvent } from "@/observability/events";
import { queryClient } from "@/query/query-client";
import { mutationAttempts } from "./mutation-attempts";
import { secureTokenStore } from "./secure-token-store";

type AuthState = "restoring" | "authenticated" | "anonymous" | "connection_error";
type AuthValue = {
  state: AuthState;
  identity: StaffIdentity | null;
  login(email: string, password: string): Promise<void>;
  logout(reason?: "manual" | "expired"): Promise<void>;
  retryRestore(): Promise<void>;
  refreshIdentity(): Promise<boolean>;
};

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [state, setState] = useState<AuthState>("restoring");
  const [identity, setIdentity] = useState<StaffIdentity | null>(null);
  const logoutPromise = useRef<Promise<void> | null>(null);

  const logout = useCallback(async (reason: "manual" | "expired" = "manual") => {
    if (logoutPromise.current) return logoutPromise.current;
    logoutPromise.current = (async () => {
      apiClient.setToken(null);
      setIdentity(null);
      mutationAttempts.clear();
      queryClient.clear();
      await secureTokenStore.clear();
      setState("anonymous");
      if (reason === "expired") recordEvent("session_expired");
    })().finally(() => { logoutPromise.current = null; });
    return logoutPromise.current;
  }, []);

  const restore = useCallback(async () => {
    setState("restoring");
    const token = await secureTokenStore.read();
    if (!token) { setState("anonymous"); return; }
    apiClient.setToken(token);
    try {
      setIdentity(await staffApi.me());
      setState("authenticated");
    } catch (error) {
      if (error instanceof StaffApiError && ["network_error", "timeout"].includes(error.code)) {
        setState("connection_error");
        return;
      }
      await logout("expired");
    }
  }, [logout]);

  useEffect(() => {
    apiClient.setInvalidTokenHandler(() => { void logout("expired"); });
    void restore();
    return () => apiClient.setInvalidTokenHandler(null);
  }, [logout, restore]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await staffApi.login(email, password);
    await secureTokenStore.write(response.access_token);
    apiClient.setToken(response.access_token);
    try {
      setIdentity(await staffApi.me());
      setState("authenticated");
      recordEvent("login_succeeded");
    } catch (error) {
      await logout();
      throw error;
    }
  }, [logout]);

  const refreshIdentity = useCallback(async () => {
    try {
      setIdentity(await staffApi.me());
      return true;
    } catch (error) {
      if (error instanceof StaffApiError && error.code === "staff_access_denied") await logout("expired");
      return false;
    }
  }, [logout]);

  const value = useMemo<AuthValue>(() => ({
    state, identity, login, logout, retryRestore: restore, refreshIdentity,
  }), [state, identity, login, logout, restore, refreshIdentity]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
