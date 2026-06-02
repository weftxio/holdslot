"use client";
import { createContext, useCallback, useContext, useRef, useState } from "react";
import clsx from "clsx";

type Kind = "ok" | "warn";
type Item = { id: number; msg: string; kind: Kind; show: boolean };

const ToastCtx = createContext<(msg: string, kind?: Kind) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const idc = useRef(0);

  const toast = useCallback((msg: string, kind: Kind = "ok") => {
    const id = ++idc.current;
    setItems((s) => [...s, { id, msg, kind, show: false }]);
    requestAnimationFrame(() =>
      setItems((s) => s.map((i) => (i.id === id ? { ...i, show: true } : i)))
    );
    setTimeout(() => {
      setItems((s) => s.map((i) => (i.id === id ? { ...i, show: false } : i)));
      setTimeout(() => setItems((s) => s.filter((i) => i.id !== id)), 300);
    }, 2600);
  }, []);

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="toast-wrap">
        {items.map((i) => (
          <div key={i.id} className={clsx("toast", i.kind === "warn" && "warn", i.show && "show")}>
            <span className="tk">{i.kind === "warn" ? "!" : "✓"}</span>
            <span>{i.msg}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
