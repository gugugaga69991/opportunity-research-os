import Link from "next/link";
import { notFound } from "next/navigation";

import { PageTitle } from "@/components/page-title";
import { Confidence, EmptyState, StatusBadge } from "@/components/ui";
import { getApi, type OpportunityDetail, timeAgo, titleCase } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function OpportunityDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const result = await getApi<OpportunityDetail | null>(`/opportunities/${id}`, null);
  if (result.online && !result.data) notFound();
  if (!result.data) {
    return (
      <div className="page-stack">
        <PageTitle eyebrow="Opportunity thesis" title="Opportunity unavailable" description="The API is offline or this opportunity no longer exists." />
        <section className="panel">
          <EmptyState title="No thesis to display" body="Reconnect the API, then reopen this opportunity from the pipeline." href="/opportunities" action="Return to pipeline" />
        </section>
      </div>
    );
  }
  const item = result.data;
  return (
    <div className="page-stack">
      <div className="breadcrumb"><Link href="/opportunities">Opportunities</Link><span>/</span><span>{item.name}</span></div>
      <PageTitle
        eyebrow={`${titleCase(item.track)} thesis · ${item.industry}`}
        title={item.name}
        description={item.value_proposition || item.problem}
        action={<StatusBadge value={item.status} />}
      />
      <div className="thesis-score">
        <div><span>Confidence</span><Confidence value={item.confidence} /></div>
        <div><span>Evidence gate</span><strong>{item.evidence_gate_passed ? "Passed" : "Pending"}</strong></div>
        <div><span>Buyer</span><strong>{item.buyer_identified ? item.buyer_role : "Unconfirmed"}</strong></div>
        <div><span>Recurrence</span><strong>{item.recurring_problem ? "Confirmed" : "Unconfirmed"}</strong></div>
      </div>
      <div className="detail-grid">
        <section className="panel thesis-panel">
          <span className="detail-label">Problem</span><h2>{item.problem}</h2>
          <div className="detail-pair"><div><span>Core workflow</span><p>{item.core_workflow}</p></div><div><span>Frequency</span><p>{item.frequency}</p></div></div>
          <div className="detail-pair"><div><span>Current workaround</span><p>{item.current_workaround}</p></div><div><span>Existing spend</span><p>{item.existing_spend}</p></div></div>
          <div className="detail-pair"><div><span>Economic cost</span><p>{item.economic_cost}</p></div><div><span>Why now</span><p>{item.why_now}</p></div></div>
          <span className="detail-label">Solution concept</span><p className="solution-copy">{item.solution_concept}</p>
        </section>
        <aside className="panel evidence-panel">
          <div className="section-heading"><div><span>Evidence ledger</span><h2>Claims that support this</h2></div></div>
          {item.evidence.length ? item.evidence.slice(0, 8).map((evidence) => (
            <article className="evidence-item" key={`${evidence.signal_id}-${evidence.claim}`}>
              <div><StatusBadge value={evidence.stance} /><span>{titleCase(evidence.evidence_type)} · {timeAgo(evidence.last_seen_at)}</span></div>
              <p>{evidence.claim}</p>
            </article>
          )) : <EmptyState title="Evidence ledger is empty" body="The thesis exists, but its supporting claims have not been attached." />}
        </aside>
      </div>
      <section className="panel timeline-panel">
        <div className="section-heading"><div><span>Decision history</span><h2>How conviction changed</h2></div></div>
        {item.transitions.length ? item.transitions.map((transition) => (
          <div className="timeline-row" key={`${transition.created_at}-${transition.to_status}`}>
            <span>{timeAgo(transition.created_at)}</span>
            <strong>{transition.from_status ? titleCase(transition.from_status) : "Created"} → {titleCase(transition.to_status)}</strong>
            <p>{transition.reason}</p>
          </div>
        )) : <EmptyState title="No state changes yet" body="Human and system decisions will create a permanent history here." />}
      </section>
    </div>
  );
}
