import Link from "next/link";

import { PageTitle } from "@/components/page-title";
import { EmptyState, StatusBadge } from "@/components/ui";
import { getApi, type Metrics, type Opportunity, type ResearchCampaign, timeAgo } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ResearchPage() {
  const [campaigns, metrics, opportunities] = await Promise.all([
    getApi<ResearchCampaign[]>("/research/campaigns?limit=100", []),
    getApi<Metrics>("/research/metrics", {}),
    getApi<Opportunity[]>("/opportunities?limit=200", []),
  ]);
  const names = new Map(opportunities.data.map((item) => [item.id, item.name]));
  return (
    <div className="page-stack">
      <PageTitle eyebrow="Specialist research" title="Pressure-test the promising ideas." description="Parallel research lanes examine money, competitors, distribution, timing, risk, and contradictions before scoring." action={<span className={campaigns.online ? "connection online" : "connection"}>{campaigns.online ? "Research connected" : "API offline"}</span>} />
      <div className="summary-strip">
        <span><strong>{metrics.data.campaigns ?? 0}</strong> campaigns</span>
        <span><strong>{metrics.data.running ?? 0}</strong> running</span>
        <span><strong>{metrics.data.completed ?? 0}</strong> completed</span>
        <span><strong>{metrics.data.active_findings ?? 0}</strong> active findings</span>
      </div>
      <section className="panel">
        <div className="section-heading"><div><span>Research campaigns</span><h2>Coverage across specialist lanes</h2></div></div>
        {campaigns.data.length ? <div className="campaign-list">{campaigns.data.map((campaign) => {
          const coverage = Math.round(campaign.coverage_score * 100);
          return (
            <Link className="campaign-row" href={`/opportunities/${campaign.opportunity_id}`} key={campaign.id}>
              <div><strong>{names.get(campaign.opportunity_id) ?? "Opportunity research"}</strong><small>Version {campaign.version} · started {timeAgo(campaign.created_at)}</small></div>
              <StatusBadge value={campaign.status} />
              <span>{campaign.completed_lane_count}/{campaign.required_lane_count}<small>lanes</small></span>
              <div className="coverage"><span style={{ width: `${coverage}%` }} /><strong>{coverage}%</strong></div>
              <span>${campaign.cost_usd.toFixed(2)}<small>model cost</small></span>
            </Link>
          );
        })}</div> : <EmptyState title="No research campaigns yet" body="An opportunity enters specialist research only after it passes the evidence-diversity gate." href="/opportunities" action="Review opportunity pipeline" />}
      </section>
    </div>
  );
}
