"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearTokens, getAccess, getMe, type Me } from "@/lib/api";
import { nameInitials } from "@/lib/initials";

type MeState = { me: Me | null; loading: boolean };

const MeCtx = createContext<MeState>({ me: null, loading: true });

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

  return <MeCtx.Provider value={{ me, loading }}>{children}</MeCtx.Provider>;
}

export const useMe = () => useContext(MeCtx);

/** Up-to-two-letter initials from a name, falling back to the email's first letter. */
export function initialsOf(me: Me | null): string {
  const fromName = me?.full_name ? nameInitials(me.full_name) : "";
  return fromName || me?.email?.[0]?.toUpperCase() || "—";
}
