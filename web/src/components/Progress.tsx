import { useEffect, useState } from "react";
import { LoaderCircle } from "lucide-react";

/** What the app is doing while it waits, step by step. The steps are the real stages of the
 *  work; they advance on a timer because the server does not report progress, so the last one
 *  stays until the answer arrives. Elapsed seconds, never a percentage. */
export function Progress({ steps, every = 3000, inline = false }: { steps: string[]; every?: number; inline?: boolean }) {
  const [start] = useState(() => Date.now());
  const [now, setNow] = useState(start);
  useEffect(() => {
    const t = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(t);
  }, []);
  const seconds = Math.floor((now - start) / 1000);
  const at = Math.min(steps.length - 1, Math.floor((now - start) / every));
  if (inline) {
    return (
      <span className="progress-inline" aria-live="polite">
        <LoaderCircle size={15} className="spin" />
        <span>{steps[at]}</span>
        {seconds >= 3 && <small>{seconds} s</small>}
      </span>
    );
  }
  return (
    <div className="progress" aria-live="polite">
      <ol>
        {steps.map((s, i) => (
          <li key={s} className={i < at ? "done" : i === at ? "current" : "next"} aria-current={i === at ? "step" : undefined}>
            {i === at ? <LoaderCircle size={14} className="spin" /> : <span className="dot" aria-hidden="true" />}
            {s}
          </li>
        ))}
      </ol>
      {seconds >= 3 && <p className="progress-time">{seconds} seconds so far. It usually takes 5 to 30.</p>}
    </div>
  );
}
