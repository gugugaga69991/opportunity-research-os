import Link from "next/link";

import { PageTitle } from "@/components/page-title";
import { EmptyState, StatusBadge } from "@/components/ui";
import { type Alert, type BuildSpec, getApi, type Metrics, type Opportunity, type PortfolioItem, timeAgo } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OperationsPage() {
  const [portfolio, alerts, specs, metrics, opportunities] = await Promise.all([
    getApi<PortfolioItem[]>("/operations/portfolio?limit=100", []),
    getApi<Alert[]>("/operations/alerts?limit=100", []),
    getApi<BuildSpec[]>("/operations/build-specs?limit=100", []),
    getApi<Metrics>("/operations/metrics", {}),
    getApi<Opportunity[]>("/opportunities?limit=200", []),
  ]);
  const names = new Map(opportunities.data.map((item) => [item.id, item.name]));
  return (
    <div className="page-stack">
      <PageTitle eyebrow="Portfolio operations" title="From conviction to a build brief." description="Monitor thesis movement, resolve alerts, remember interviews, and hand validated opportunities into product development." action={<span className={portfolio.online ? "connection online" : "connection"}>{portfolio.online ? "Portfolio live" : "API offline"}</span>} />
      <div className="summary-strip">
        <span><strong>{metrics.data.portfolio ?? 0}</strong> tracked</span>
        <span><strong>{metrics.data.unread_alerts ?? 0}</strong> unread alerts</span>
        <span><strong>{metrics.data.interviews ?? 0}</strong> interviews</span>
        <span><strong>{metrics.data.build_specs ?? 0}</strong> build specs</span>
      </div>
      <div className="operations-grid">
        <section className="panel">
          <div className="section-heading"><div><span>Ranked portfolio</span><h2>Where conviction is moving</h2></div></div>
          {portfolio.data.length ? <div className="ops-list">{portfolio.data.map((item) => (
            <Link href={`/opportunities/${item.opportunity_id}`} className="ops-row" key={item.id}>
              <strong>#{item.rank ?? "—"}</strong><div><strong>{names.get(item.opportunity_id) ?? "Tracked opportunity"}</strong><small>{item.reasons[0] ?? "Portfolio assessment complete"}</small></div><StatusBadge value={item.state} /><span className={item.score_velocity >= 0 ? "movement up" : "movement down"}>{item.score_velocity >= 0 ? "↗" : "↘"} {Math.abs(item.score_velocity).toFixed(1)}</span><strong>{item.current_score.toFixed(1)}</strong>
            </Link>
          ))}</div> : <EmptyState title="Nothing is being monitored" body="Scored opportunities enter the portfolio after the first decision cycle." />}
        </section>
        <aside className="panel">
          <div className="section-heading"><div><span>Operational alerts</span><h2>Changes worth seeing</h2></div></div>
          {alerts.data.length ? <div className="alert-list">{alerts.data.slice(0, 10).map((alert) => (
            <article className="alert-item" key={alert.id}><span className={`severity ${alert.severity}`} /><div><span>{timeAgo(alert.created_at)}</span><strong>{alert.title}</strong><p>{alert.message}</p></div></article>
          ))}</div> : <EmptyState title="No operational alerts" body="Pain spikes, ranking changes, competitor moves, and stale research will appear here." />}
        </aside>
      </div>
      <section className="panel">
        <div className="section-heading"><div><span>Build handoff</span><h2>Approved product briefs</h2></div></div>
        {specs.data.length ? <div className="spec-grid">{specs.data.map((spec) => (
          <article className="spec-card" key={spec.id}><StatusBadge value={spec.status} /><h3>{names.get(spec.opportunity_id) ?? "Opportunity build specification"}</h3><p>Version {spec.version} · generated {timeAgo(spec.created_at)}</p><a className="text-link" href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/operations/build-specs/${spec.id}/markdown`}>Download build brief →</a></article>
        ))}</div> : <EmptyState title="No build brief has been generated" body="A candidate reaches build handoff only after research, scoring, and real-world validation are complete." />}
      </section>
    </div>
  );
}
