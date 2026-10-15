import type { ReactNode } from "react";

/** Greek key (meander) band, drawn as a repeating SVG pattern. */
export function Meander({ className = "rule" }: { className?: string }) {
  return (
    <svg className={className} preserveAspectRatio="none" aria-hidden>
      <defs>
        <pattern id="meander" width="12" height="9" patternUnits="userSpaceOnUse">
          <path
            d="M0 8.5 H10.5 V0.5 H2.5 V6 H8 V3 H5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1"
          />
        </pattern>
      </defs>
      <rect width="100%" height="100%" fill="url(#meander)" />
    </svg>
  );
}

/** An almond eye in the black-figure manner: gold outline, ember iris. */
export function EyeGlyph({ size = 22, lit = false }: { size?: number; lit?: boolean }) {
  return (
    <svg width={size} height={size * 0.62} viewBox="0 0 64 40" aria-hidden style={{ overflow: "visible" }}>
      <path d="M3 20 Q32 -6 61 20 Q32 46 3 20Z" fill="#0b0908" stroke="#d6a04c" strokeWidth="2.6" />
      <circle cx="32" cy="20" r="11" fill="#5a1c0a" stroke={lit ? "#ff8a2a" : "#b4521c"} strokeWidth="2.4" />
      <circle cx="32" cy="20" r="4.6" fill="#000" />
      <circle cx="35.5" cy="16.5" r="1.8" fill="#efe4cc" opacity=".85" />
      {lit && <circle cx="32" cy="20" r="11" fill="none" stroke="#ff8a2a" strokeWidth="1" opacity=".6">
        <animate attributeName="r" values="11;17;11" dur="2.6s" repeatCount="indefinite" />
        <animate attributeName="opacity" values=".6;0;.6" dur="2.6s" repeatCount="indefinite" />
      </circle>}
    </svg>
  );
}

export function Panel({
  num,
  title,
  meta,
  glow,
  className = "",
  children,
}: {
  num?: string;
  title: string;
  meta?: ReactNode;
  glow?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`panel ${glow ? "glow" : ""} ${className}`}>
      <span className="corner tl" />
      <span className="corner tr" />
      <span className="corner bl" />
      <span className="corner br" />
      <header className="ph">
        {num && <span className="num">{num}</span>}
        <span className="title">{title}</span>
        <Meander />
        {meta && <span className="meta">{meta}</span>}
      </header>
      {children}
    </section>
  );
}
