import type { Cluster, Opportunity } from "@/lib/api";

const fallbackBars = [8, 12, 10, 17, 14, 23, 18, 31, 26, 38, 34, 47, 41, 52, 46, 61];

export function EvidenceHorizon({
  clusters,
  opportunities,
}: {
  clusters: Cluster[];
  opportunities: Opportunity[];
}) {
  const sourceBreadth = clusters.reduce((sum, cluster) => sum + cluster.source_count, 0);
  const pain = clusters.filter((cluster) => cluster.cluster_type === "pain").length;
  const recurring = opportunities.filter((item) => item.recurring_problem).length;
  const momentum = clusters.reduce((sum, cluster) => sum + cluster.velocity_30d, 0);
  const bars = clusters.length
    ? Array.from({ length: 16 }, (_, index) => {
        const cluster = clusters[index % clusters.length];
        return Math.max(8, Math.min(92, Math.round(cluster.corroboration_score * 65 + cluster.velocity_30d * 3)));
      })
    : fallbackBars;

  return (
    <section className="horizon-panel">
      <div className="horizon-copy">
        <span className="eyebrow">Evidence horizon / live corpus</span>
        <h1>
          Find the workflow
          <br />
          people already pay to fix.
        </h1>
        <p>
          The system ranks recurring pain only after it survives source diversity,
          contradiction, buyer, and timing checks.
        </p>
      </div>
      <div className="horizon-visual" aria-label="Evidence momentum visualization">
        <div className="horizon-bars">
          {bars.map((height, index) => (
            <i
              key={`${height}-${index}`}
              style={{ height: `${height}%`, animationDelay: `${index * 45}ms` }}
            />
          ))}
        </div>
        <div className="horizon-axis">
          <span>earlier signals</span>
          <span>current edge</span>
        </div>
      </div>
      <div className="horizon-stats">
        <div>
          <span>Source breadth</span>
          <strong>{sourceBreadth}</strong>
        </div>
        <div>
          <span>Pain clusters</span>
          <strong>{pain}</strong>
        </div>
        <div>
          <span>Recurring</span>
          <strong>{recurring}</strong>
        </div>
        <div>
          <span>30d momentum</span>
          <strong>{momentum.toFixed(1)}</strong>
        </div>
      </div>
    </section>
  );
}
