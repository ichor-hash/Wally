"use client";

import { createContext, useCallback, useContext, useRef, useState, ReactNode } from "react";

type ToastKind = "success" | "error" | "info" | "warning";

interface Toast {
  id: number;
  kind: ToastKind;
  title: string;
  description?: string;
}

interface ToastApi {
  toast: (kind: ToastKind, title: string, description?: string) => void;
}

const ToastContext = createContext<ToastApi>({ toast: () => {} });

export const useToast = () => useContext(ToastContext);

const DOT: Record<ToastKind, string> = {
  success: "bg-[#7fd1a0]",
  error: "bg-[#ff8a80]",
  warning: "bg-[#f5c46b]",
  info: "bg-[#bdbdbd]",
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (kind: ToastKind, title: string, description?: string) => {
      const id = nextId.current++;
      setToasts((prev) => [...prev.slice(-3), { id, kind, title, description }]);
      setTimeout(() => dismiss(id), kind === "error" ? 7000 : 4200);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex flex-col items-center gap-2 px-4" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className="rise pointer-events-auto flex w-full max-w-[420px] items-start gap-3 rounded-xl bg-[#1a1a1a] px-4 py-3 text-white shadow-[0_12px_32px_-12px_rgba(0,0,0,0.45)]"
          >
            <span className={`mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full ${DOT[t.kind]}`} />
            <div className="min-w-0 flex-1">
              <p className="text-[13.5px] font-medium">{t.title}</p>
              {t.description && <p className="mt-0.5 break-words text-[12.5px] leading-snug text-white/60">{t.description}</p>}
            </div>
            <button onClick={() => dismiss(t.id)} className="text-[12px] text-white/50 hover:text-white" aria-label="Dismiss">
              Close
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
