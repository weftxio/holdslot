"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearTokens, getAccess, getMe, type Me } from "@/lib/api";
import { nameInitials } from "@/lib/initials";

type MeState = { me: Me | null; loading: boolean; refetch: () => Promise<void> };

const MeCtx = createContext<MeState>({ me: null, loading: true, refetch: async () => {} });

/**
 * Loads the signed-in user from the live API once on mount and shares it with the console
 * shell. Doubles as the console's auth gate: no token (or a rejected one) → back to /login.
 */
export function MeProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!getAccess()) {
      router.replace("/login");
      return;
    }
    getMe()
      .then(setMe)
      .catch(() => {
        clearTokens();
        router.replace("/login");
      })
      .finally(() => setLoading(false));
  }, [router]);

  // N45 — refresh /me on demand (e.g. after creating a client) so consumers like the client switcher
  // reflect the new tenant without a full reload. A failure here is non-fatal — keep the current me.
  const refetch = useCallback(async () => {
    if (!getAccess()) return;
    try {
      setMe(await getMe());
    } catch {
      /* keep the last-known me; the console guard handles a truly dead session */
    }
  }, []);

  return <MeCtx.Provider value={{ me, loading, refetch }}>{children}</MeCtx.Provider>;
}

export const useMe = () => useContext(MeCtx);

/** Up-to-two-letter initials from a name, falling back to the email's first letter. */
export function initialsOf(me: Me | null): string {
  const fromName = me?.full_name ? nameInitials(me.full_name) : "";
  return fromName || me?.email?.[0]?.toUpperCase() || "—";
}
