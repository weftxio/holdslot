"use client";
import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { clearTokens, getAccess, getMe, type Me } from "@/lib/api";

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
  if (me?.full_name) {
    return me.full_name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((p) => p[0]!.toUpperCase())
      .join("");
  }
  return me?.email?.[0]?.toUpperCase() ?? "—";
}
