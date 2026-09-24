import { PageTitle } from "@/components/page-title";
import { EmptyState, StatusBadge } from "@/components/ui";
import { type Cluster, getApi, type Metrics, type Signal, timeAgo, titleCase } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function SignalsPage() {
  const [signals, clusters, metrics] = await Promise.all([
    getApi<Signal[]>("/processing/signals?limit=100", []),
    getApi<Cluster[]>("/intelligence/clusters?limit=50", []),
    getApi<Metrics>("/processing/metrics", {}),
  ]);
  return (
    <div className="page-stack">
      <PageTitle eyebrow="Signal lake" title="Raw noise becomes usable evidence." description="Every source is normalized, deduplicated, classified, and kept traceable to the original document." action={<span className={signals.online ? "connection online" : "connection"}>{signals.online ? "Ingesting" : "API offline"}</span>} />
      <div className="summary-strip">
        <span><strong>{metrics.data.total_documents ?? 0}</strong> documents</span>
        <span><strong>{metrics.data.total_signals ?? 0}</strong> signals</span>
        <span><strong>{metrics.data.duplicates ?? 0}</strong> duplicates removed</span>
        <span><strong>{metrics.data.pains ?? 0}</strong> pain signals</span>
      </div>
      <div className="signal-layout">
        <section className="panel">
          <div className="section-heading"><div><span>Pattern intelligence</span><h2>Corroborated clusters</h2></div></div>
          {clusters.data.length ? <div className="cluster-list">{clusters.data.map((cluster) => (
            <article className="cluster-card" key={cluster.id}>
              <div><StatusBadge value={cluster.cluster_type} /><span>{cluster.velocity_30d > 0 ? "↗" : "→"} {cluster.velocity_30d.toFixed(1)} velocity</span></div>
              <h3>{cluster.title}</h3><p>{cluster.summary}</p>
              <footer><span>{cluster.signal_count} signals</span><span>{cluster.source_count} sources</span><strong>{Math.round(cluster.corroboration_score * 100)}% corroborated</strong></footer>
            </article>
          ))}</div> : <EmptyState title="No patterns have formed yet" body="Clusters appear once multiple signals share a workflow, pain, workaround, or market-change pattern." />}
        </section>
        <aside className="panel">
          <div className="section-heading"><div><span>Recent intake</span><h2>Signal feed</h2></div></div>
          {signals.data.length ? <div className="feed-list">{signals.data.slice(0, 20).map((signal) => (
            <article className="feed-item" key={signal.id}>
              <div><StatusBadge value={signal.status} /><span>{timeAgo(signal.created_at)}</span></div>
              <strong>{signal.is_duplicate ? titleCase(signal.duplicate_kind ?? "duplicate") : "Unique evidence retained"}</strong>
              <small>{signal.language.toUpperCase()} · {signal.id.slice(0, 8)}</small>
            </article>
          ))}</div> : <EmptyState title="No signals received" body="Approve and schedule a collection source to start filling the evidence lake." />}
        </aside>
      </div>
    </div>
  );
}
