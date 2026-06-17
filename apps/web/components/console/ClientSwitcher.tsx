"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import clsx from "clsx";
import {
  addClient,
  DEFAULT_CLIENTS,
  DEFAULT_CLIENT_PAGE,
  loadClients,
  saveClients,
  slugify,
  type Client,
} from "@/lib/client";

export function ClientSwitcher({ currentSlug }: { currentSlug: string }) {
  const router = useRouter();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [list, setList] = useState<Client[]>(DEFAULT_CLIENTS);
  const [open, setOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => setList(loadClients()), []);
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
  function create() {
    if (!newName.trim()) return;
    const c = addClient(list, newName);
    const next = [...list, c];
    setList(next);
    saveClients(next);
    setNewName("");
    setCreateOpen(false);
    select(c.slug);
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
          <button className="cc-go" type="button" onClick={create}>
            Create client
          </button>
        </div>
      </div>
    </div>
  );
}
