"use client";
/* A panel that folds away.

   The incident view is six stacked panels and the farm floor above them, which
   is more than fits on a screen and more than anyone needs at once. Folding is
   per-panel and remembered, so an operator who only ever wants the diagnosis
   gets the diagnosis.

   Two rules this holds to:

     · a folded panel still says what it is hiding. `meta` stays visible in the
       header, so collapsing changes how much room something takes, never
       whether you know it is there — a folded panel that reads as empty would
       quietly hide a failure.
     · the stored preference is read after mount, not during render. Reading
       localStorage while rendering makes the server and client disagree about
       the first paint, and React refuses to patch that tree. */

import { useEffect, useState } from "react";

export function Section({
  id,
  title,
  meta,
  defaultOpen = true,
  className = "",
  children,
}: {
  /** Stable key for remembering this panel's state. */
  id: string;
  title: React.ReactNode;
  /** Stays visible when folded — the summary you are collapsing down to. */
  meta?: React.ReactNode;
  defaultOpen?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(`genesis.section.${id}`);
      if (stored !== null) setOpen(stored === "1");
    } catch { /* private mode — the default stands */ }
  }, [id]);

  const toggle = () => {
    setOpen((was) => {
      const next = !was;
      try { localStorage.setItem(`genesis.section.${id}`, next ? "1" : "0"); }
      catch { /* preference simply is not remembered */ }
      return next;
    });
  };

  return (
    <section className={`panel section${open ? "" : " folded"} ${className}`}>
      <h2 className="sec-head">
        <button
          type="button"
          className="sec-toggle"
          onClick={toggle}
          aria-expanded={open}
          aria-controls={`sec-${id}`}
        >
          <span className="sec-caret" aria-hidden="true">▸</span>
          <span className="sec-title">{title}</span>
        </button>
        {meta && <span className="sec-meta">{meta}</span>}
      </h2>
      {open && <div className="sec-body" id={`sec-${id}`}>{children}</div>}
    </section>
  );
}
