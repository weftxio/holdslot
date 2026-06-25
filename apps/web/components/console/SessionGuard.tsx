"use client";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { accessExpiresAt, refreshAccess, clearTokens } from "@/lib/api";

// "Active" = a pointer/key interaction within this window before the token expires. An active
// user's lapsed token is renewed silently; an idle portal is logged out at expiry.
const IDLE_GRACE_MS = 5 * 60 * 1000;

/**
 * Watches the access-token expiry while the console is open:
 *  · active user at expiry → silent refresh, session continues (no interruption)
 *  · idle portal at expiry → force logout to /login?expired=1
 * Re-arms whenever the token changes (login / silent refresh) and re-checks on tab focus,
 * since background timers don't fire while the tab is hidden or the machine is asleep.
 */
export function SessionGuard() {
  const router = useRouter();
  // Seeded in the mount effect, not here — calling Date.now() during render is impure.
  const lastActivity = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    lastActivity.current = Date.now(); // mounting the guard counts as the first activity
    const markActive = () => {
      lastActivity.current = Date.now();
    };

    function forceLogout() {
      clearTokens();
      router.replace("/login?expired=1");
    }

    function onExpiry() {
      if (Date.now() - lastActivity.current > IDLE_GRACE_MS) {
        forceLogout(); // idle at expiry — end the session
        return;
      }
      // Still working — renew silently. "ok" re-arms via the `holdslot:tokens` emit; a genuinely
      // dead session logs out; a transient blip retries shortly rather than dropping the user.
      refreshAccess().then((res) => {
        if (res === "expired") forceLogout();
        else if (res === "error") timer.current = setTimeout(onExpiry, 30_000);
      });
    }

    function arm() {
      if (timer.current) clearTimeout(timer.current);
      const exp = accessExpiresAt();
      if (exp === null) return; // no token — MeProvider owns that redirect
      const delay = exp - Date.now();
      if (delay <= 0) onExpiry();
      else timer.current = setTimeout(onExpiry, delay + 1000); // +1s so the token is truly expired
    }

    function onFocus() {
      const exp = accessExpiresAt();
      if (exp !== null && exp - Date.now() <= 0) onExpiry();
      else arm();
    }

    arm();
    window.addEventListener("pointerdown", markActive);
    window.addEventListener("keydown", markActive);
    window.addEventListener("holdslot:tokens", arm);
    window.addEventListener("holdslot:auth-expired", forceLogout);
    document.addEventListener("visibilitychange", onFocus);
    window.addEventListener("focus", onFocus);
    return () => {
      if (timer.current) clearTimeout(timer.current);
      window.removeEventListener("pointerdown", markActive);
      window.removeEventListener("keydown", markActive);
      window.removeEventListener("holdslot:tokens", arm);
      window.removeEventListener("holdslot:auth-expired", forceLogout);
      document.removeEventListener("visibilitychange", onFocus);
      window.removeEventListener("focus", onFocus);
    };
  }, [router]);

  return null;
}
