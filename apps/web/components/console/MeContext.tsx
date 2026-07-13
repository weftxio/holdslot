"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, clearTokens, getAccess, getMe, type Me } from "@/lib/api";
import { nameInitials } from "@/lib/initials";

type MeState = { me: Me | null; loading: boolean; refetch: () => Promise<void> };

const MeCtx = createContext<MeState>({ me: null, loading: true, refetch: async () => {} });

/**
 * Loads the signed-in user from the live API once on mount and shares it with the console
 * shell. Doubles as the console's auth gate: no token (or a genuinely rejected one) → back to
 * /login. A cold-start 5xx / network blip is NOT a rejection (M4) — see the catch below.
 */
export function MeProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [reloadNonce, setReloadNonce] = useState(0);

  useEffect(() => {
    if (!getAccess()) {
      router.replace("/login");
      return;
    }
    let alive = true;
    getMe()
      .then((m) => alive && setMe(m))
      .catch((e) => {
        if (!alive) return;
        // Only a real auth failure ends the session. Dev Aurora auto-pauses, so `/me` on first
        // console open routinely returns a cold-start 503 (or a network blip) — clearing tokens
        // there forced a needless re-login (M4). Keep the tokens and show a retry instead; a truly
        // dead session is handled by the `holdslot:auth-expired` event the authFetch layer emits
        // (SessionGuard turns it into the redirect).
        if (e instanceof ApiError && e.status === 401) {
          clearTokens();
          router.replace("/login");
        } else {
          setLoadError(true);
        }
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [router, reloadNonce]);

  // N45 — refresh /me on demand (e.g. after creating a client) so consumers like the client switcher
  // reflect the new tenant without a full reload. A failure here is non-fatal — keep the current me.
  const refetch = useCallback(async () => {
    if (!getAccess()) return;
    try {
      setMe(await getMe());
      setLoadError(false);
    } catch {
      /* keep the last-known me; the console guard handles a truly dead session */
    }
  }, []);

  // A transient `/me` failure with nothing to fall back on: keep the session, offer a retry (M4).
  const retry = () => {
    setLoading(true);
    setLoadError(false);
    setReloadNonce((n) => n + 1);
  };
  if (loadError && !me && !loading) {
    return <MeLoadError onRetry={retry} />;
  }

  return <MeCtx.Provider value={{ me, loading, refetch }}>{children}</MeCtx.Provider>;
}

/** Full-pane "couldn't reach the server" retry — shown when `/me` fails transiently (never a forced
 *  logout). Uses design-system classes only; no new CSS. */
function MeLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        padding: 24,
        textAlign: "center",
      }}
    >
      <div>
        <h2 style={{ marginBottom: 8 }}>We couldn&apos;t reach the server</h2>
        <p className="muted" style={{ marginBottom: 20, maxWidth: 420 }}>
          It may be waking up. Your session is still signed in — try again in a moment.
        </p>
        <button className="btn btn-primary" onClick={onRetry}>
          Try again
        </button>
      </div>
    </div>
  );
}

export const useMe = () => useContext(MeCtx);

/** Up-to-two-letter initials from a name, falling back to the email's first letter. */
export function initialsOf(me: Me | null): string {
  const fromName = me?.full_name ? nameInitials(me.full_name) : "";
  return fromName || me?.email?.[0]?.toUpperCase() || "—";
}
