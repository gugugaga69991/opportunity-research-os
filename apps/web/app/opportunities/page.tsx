import Link from "next/link";

import { PageTitle } from "@/components/page-title";
import { Confidence, EmptyState, StatusBadge } from "@/components/ui";
import { getApi, type Opportunity, titleCase } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OpportunitiesPage() {
  const result = await getApi<Opportunity[]>("/opportunities?limit=200", []);
  const gated = result.data.filter((item) => item.evidence_gate_passed).length;
  const contradicted = result.data.filter((item) => item.contradiction_count > 0).length;

  return (
    <div className="page-stack">
      <PageTitle
        eyebrow="Opportunity pipeline"
        title="Evidence before enthusiasm."
        description="Every candidate stays provisional until recurrence, source diversity, buyer, and contradiction checks agree."
        action={<span className={result.online ? "connection online" : "connection"}>{result.online ? "Live" : "API offline"}</span>}
      />
      <div className="summary-strip">
        <span><strong>{result.data.length}</strong> total</span>
        <span><strong>{gated}</strong> evidence-gated</span>
        <span><strong>{contradicted}</strong> with contradictions</span>
        <span><strong>{result.data.filter((item) => item.status === "build").length}</strong> ready to build</span>
      </div>
      <section className="panel">
        <div className="filter-row" aria-label="Opportunity filters">
          <span className="filter active">All candidates</span>
          <span className="filter">Pain-led</span>
          <span className="filter">Change-led</span>
          <span className="filter">Research-ready</span>
          <span className="filter">Build</span>
        </div>
        {result.data.length ? (
          <div className="candidate-grid">
            {result.data.map((item) => (
              <Link className="candidate-card" href={`/opportunities/${item.id}`} key={item.id}>
                <div className="candidate-top">
                  <span>{titleCase(item.track)}</span>
                  <StatusBadge value={item.status} />
                </div>
                <h2>{item.name}</h2>
                <p>{item.problem}</p>
                <div className="candidate-meta">
                  <span>{item.industry}</span>
                  <span>{item.icp}</span>
                </div>
                <div className="evidence-ledger">
                  <span><strong>{item.confirming_signal_count}</strong> signals</span>
                  <span><strong>{item.confirming_source_count}</strong> sources</span>
                  <span><strong>{item.contradiction_count}</strong> contradictions</span>
                </div>
                <Confidence value={item.confidence} />
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState
            title="The pipeline is waiting for corroborated pain"
            body="Candidates will appear after the collection and intelligence layers find a workflow pattern across multiple sources."
            href="/signals"
            action="Review source evidence"
          />
        )}
      </section>
    </div>
  );
}
