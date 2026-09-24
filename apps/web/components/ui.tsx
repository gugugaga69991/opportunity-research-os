import Link from "next/link";
import type { ReactNode } from "react";

import { titleCase } from "@/lib/api";

export function StatusBadge({ value }: { value: string }) {
  const tone = ["failed", "blocked", "killed", "critical"].some((word) =>
    value.includes(word),
  )
    ? "danger"
    : ["succeeded", "completed", "build", "improving"].some((word) =>
          value.includes(word),
        )
      ? "success"
      : ["running", "researching", "corroborating"].some((word) =>
            value.includes(word),
          )
        ? "active"
        : "neutral";
  return <span className={`status-badge ${tone}`}>{titleCase(value)}</span>;
}

export function SectionHeading({
  eyebrow,
  title,
  action,
}: {
  eyebrow: string;
  title: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        <span>{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  title,
  body,
  href,
  action,
}: {
  title: string;
  body: string;
  href?: string;
  action?: string;
}) {
  return (
    <div className="empty-state">
      <span className="empty-scan" aria-hidden="true" />
      <strong>{title}</strong>
      <p>{body}</p>
      {href && action ? (
        <Link className="text-link" href={href}>
          {action} <span aria-hidden="true">→</span>
        </Link>
      ) : null}
    </div>
  );
}

export function Confidence({ value }: { value: number }) {
  const percent = Math.round(value * 100);
  return (
    <div className="confidence" aria-label={`${percent}% confidence`}>
      <span style={{ width: `${percent}%` }} />
      <strong>{percent}</strong>
    </div>
  );
}
