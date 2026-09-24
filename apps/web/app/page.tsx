import Link from "next/link";

import { EvidenceHorizon } from "@/components/evidence-horizon";
import {
  Confidence,
  EmptyState,
  SectionHeading,
  StatusBadge,
} from "@/components/ui";
import {
  type Alert,
  type Cluster,
  getApi,
  type Metrics,
  type Opportunity,
  type PortfolioItem,
  timeAgo,
  titleCase,
} from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OverviewPage() {
  const [opportunities, clusters, processing, research, alerts, portfolio] =
    await Promise.all([
      getApi<Opportunity[]>("/opportunities?limit=8", []),
      getApi<Cluster[]>("/intelligence/clusters?limit=20", []),
      getApi<Metrics>("/processing/metrics", {}),
      getApi<Metrics>("/research/metrics", {}),
      getApi<Alert[]>("/operations/alerts?status=unread&limit=5", []),
      getApi<PortfolioItem[]>("/operations/portfolio?limit=8", []),
    ]);

  const online = [opportunities, clusters, processing, research].every(
    (result) => result.online,
  );
  const opportunityById = new Map(
    opportunities.data.map((item) => [item.id, item]),
  );

  return (
    <div className="page-stack">
      <div className="page-meta">
        <div>
          <span className={online ? "connection online" : "connection"}>
            {online ? "Live evidence connected" : "Waiting for API"}
          </span>
          <span>Last view refresh: now</span>
        </div>
        <Link className="button secondary" href="/research">
          Open research inbox
        </Link>
      </div>

      <EvidenceHorizon
        clusters={clusters.data}
        opportunities={opportunities.data}
      />

      <section className="metric-grid" aria-label="System metrics">
        <Metric
          label="Signals retained"
          value={processing.data.total_signals ?? 0}
          detail={`${processing.data.duplicates ?? 0} duplicates removed`}
        />
        <Metric
          label="Pain evidence"
          value={processing.data.pains ?? 0}
          detail={`${processing.data.awaiting_model ?? 0} awaiting analysis`}
        />
        <Metric
          label="Research complete"
          value={research.data.completed ?? 0}
          detail={`${research.data.running ?? 0} campaigns active`}
        />
        <Metric
          label="Evidence-gated"
          value={opportunities.data.filter((item) => item.evidence_gate_passed).length}
          detail={`${opportunities.data.length} visible opportunities`}
        />
      </section>

      <div className="overview-grid">
        <section className="panel opportunity-panel">
          <SectionHeading
            eyebrow="Ranked opportunity queue"
            title="What deserves attention"
            action={
              <Link className="text-link" href="/opportunities">
                View pipeline →
              </Link>
            }
          />
          {opportunities.data.length ? (
            <div className="opportunity-list">
              {opportunities.data.slice(0, 6).map((item, index) => (
                <Link
                  className="opportunity-row"
                  href={`/opportunities/${item.id}`}
                  key={item.id}
                >
                  <span className="rank">{String(index + 1).padStart(2, "0")}</span>
                  <span className="opportunity-main">
                    <strong>{item.name}</strong>
                    <small>
                      {item.industry} · {item.icp}
                    </small>
                  </span>
                  <StatusBadge value={item.status} />
                  <span className="signal-count">
                    {item.confirming_signal_count}
                    <small>signals</small>
                  </span>
                  <Confidence value={item.confidence} />
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="No opportunity has cleared the evidence gate"
              body="Connect a source and run the research cycle. Candidates appear only after corroborated workflow pain is detected."
              href="/signals"
              action="Inspect signal intake"
            />
          )}
        </section>

        <aside className="panel alert-panel">
          <SectionHeading eyebrow="Attention required" title="Research inbox" />
          {alerts.data.length ? (
            <div className="alert-list">
              {alerts.data.map((alert) => (
                <article className="alert-item" key={alert.id}>
                  <span className={`severity ${alert.severity}`} />
                  <div>
                    <span>
                      {titleCase(alert.alert_type)} · {timeAgo(alert.created_at)}
                    </span>
                    <strong>{alert.title}</strong>
                    <p>{alert.message}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Inbox is clear"
              body="Contradictions, sudden pain spikes, and decisions needing review will land here."
            />
          )}
        </aside>
      </div>

      <section className="panel portfolio-panel">
        <SectionHeading
          eyebrow="Portfolio movement"
          title="Conviction is allowed to change"
          action={
            <Link className="text-link" href="/operations">
              Open operations →
            </Link>
          }
        />
        {portfolio.data.length ? (
          <div className="portfolio-table table-scroll">
            <div className="table-header">
              <span>Rank</span>
              <span>Opportunity</span>
              <span>State</span>
              <span>Score</span>
              <span>Pain velocity</span>
              <span>Movement</span>
            </div>
            {portfolio.data.map((item) => {
              const opportunity = opportunityById.get(item.opportunity_id);
              return (
                <Link
                  className="table-row"
                  href={`/opportunities/${item.opportunity_id}`}
                  key={item.id}
                >
                  <strong>#{item.rank ?? "—"}</strong>
                  <span>
                    <strong>{opportunity?.name ?? "Tracked opportunity"}</strong>
                    <small>{opportunity?.industry ?? item.opportunity_id.slice(0, 8)}</small>
                  </span>
                  <StatusBadge value={item.state} />
                  <strong>{item.current_score.toFixed(1)}</strong>
                  <span>{item.pain_velocity > 0 ? "+" : ""}{item.pain_velocity.toFixed(1)}</span>
                  <span className={item.score_velocity >= 0 ? "movement up" : "movement down"}>
                    {item.score_velocity >= 0 ? "↗" : "↘"} {Math.abs(item.score_velocity).toFixed(1)}
                  </span>
                </Link>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="Portfolio begins after scoring"
            body="Scored opportunities will be ranked here with pain, competition, and timing movement."
          />
        )}
      </section>
    </div>
  );
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <article className="metric">
      <span>{label}</span>
      <strong>{value.toLocaleString()}</strong>
      <small>{detail}</small>
    </article>
  );
}
