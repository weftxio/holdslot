"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { useMe } from "@/components/console/MeContext";
import { createClient } from "@/lib/api";
import { DEFAULT_CLIENTS, DEFAULT_CLIENT_PAGE, slugify, type Client } from "@/lib/client";

export function ClientSwitcher({ currentSlug }: { currentSlug: string }) {
  const router = useRouter();
  const toast = useToast();
  const { me, refetch } = useMe();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  // L16 — a slug we just created but that a failed /me refetch hasn't surfaced yet must NOT be
  // bounced by the M32 effect below; and the zero-membership notice should fire at most once.
  const createdSlugRef = useRef<string | null>(null);
  const zeroNotifiedRef = useRef(false);

  // N45 — the client list is the caller's real memberships from /me (the single source of truth),
  // not a localStorage cache. Before /me resolves, show the current slug so the switcher never blanks.
  const list: Client[] =
    me?.clients.map((c) => ({ name: c.name, slug: c.slug })) ??
    (currentSlug ? [{ name: currentSlug, slug: currentSlug }] : DEFAULT_CLIENTS);

  // M32 — a slug the caller isn't a member of would otherwise render as a normal "current client"
  // while every API call under it 403/404-toasts. Once `me` resolves, bounce an unknown slug to the
  // caller's first real client instead of stranding them on a dead workspace.
  useEffect(() => {
    if (!me) return;
    const slugs = me.clients.map((c) => c.slug);
    if (!slugs.length) {
      // L16 — a zero-membership user would otherwise sit on a dead workspace with no explanation
      // (M32 promised a notice). Surface it once; the account has no client to bounce to.
      if (!zeroNotifiedRef.current) {
        zeroNotifiedRef.current = true;
        toast("Your account has no client workspaces yet — create one to get started.", "warn");
      }
      return;
    }
    // L16 — don't bounce a slug we just created but that a failed /me refetch hasn't surfaced yet;
    // createClient already enrolled the caller as owner, so /me will catch up.
    if (currentSlug === createdSlugRef.current) return;
    if (!slugs.includes(currentSlug)) {
      router.replace(`/${me.clients[0].slug}/${DEFAULT_CLIENT_PAGE}`);
    }
  }, [me, currentSlug, router, toast]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("click", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const current = list.find((c) => c.slug === currentSlug) || {
    name: currentSlug,
    slug: currentSlug,
  };

  function select(slug: string) {
    setOpen(false);
    router.push(`/${slug}/${DEFAULT_CLIENT_PAGE}`);
  }
  async function create() {
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      // N45 — create a REAL tenant (POST /clients enrolls the caller as owner) and navigate to the
      // server-assigned slug. Refetch /me first so the new client is in the list the target route
      // authorizes against — the old local-only create navigated to a slug with no membership → 404.
      const created = await createClient(name);
      // L16 — mark the new slug before navigating so the M32 bounce effect can't strand us on it if
      // the /me refetch blips; then refetch (which now reports success) to surface it in the list.
      createdSlugRef.current = created.slug;
      const refreshed = await refetch();
      setNewName("");
      setCreateOpen(false);
      select(created.slug);
      if (!refreshed) toast("Client created — your list will refresh shortly.", "ok");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn’t create the client", "warn");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className={clsx("client-switch", open && "open")} ref={wrapRef}>
      <button
        className="client-btn"
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
      >
        <span className="c-av">{current.name.charAt(0).toUpperCase()}</span>
        <span className="c-info">
          <span className="c-name">{current.name}</span>
          <span className="c-slug">holdslot.com/{current.slug}</span>
        </span>
        <span className="c-caret">▾</span>
      </button>
      <div className="client-menu">
        {list.map((c) => (
          <button
            key={c.slug}
            className={clsx("client-opt", c.slug === currentSlug && "on")}
            type="button"
            onClick={() => select(c.slug)}
          >
            <span className="co-name">{c.name}</span>
            <span className="co-slug">/{c.slug}</span>
          </button>
        ))}
        <div className="client-div" />
        <button className="cc-toggle" type="button" onClick={() => setCreateOpen((o) => !o)}>
          ＋ Create new client
        </button>
        <div className={clsx("client-create-form", createOpen && "show")}>
          <input
            type="text"
            placeholder="Client name"
            maxLength={40}
            autoComplete="off"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), create())}
          />
          <div className="cc-slug">
            URL slug: holdslot.com/<b className="cc-slugval">{slugify(newName) || "client"}</b>
          </div>
          <button className="cc-go" type="button" onClick={create} disabled={creating}>
            {creating ? "Creating…" : "Create client"}
          </button>
        </div>
      </div>
    </div>
  );
}
