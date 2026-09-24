const API_URL =
  process.env.API_INTERNAL_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

export type Opportunity = {
  id: string;
  name: string;
  industry: string;
  icp: string;
  user_role: string;
  buyer_role: string;
  problem: string;
  solution_concept: string;
  track: string;
  status: string;
  readiness: string;
  confidence: number;
  confirming_signal_count: number;
  confirming_source_count: number;
  evidence_type_count: number;
  contradiction_count: number;
  buyer_identified: boolean;
  recurring_problem: boolean;
  evidence_gate_passed: boolean;
  updated_at: string;
};

export type OpportunityDetail = Opportunity & {
  core_workflow: string;
  frequency: string;
  current_workaround: string;
  economic_cost: string;
  existing_spend: string;
  why_now: string;
  desired_outcome: string;
  value_proposition: string;
  thesis: Record<string, unknown>;
  genealogy: Record<string, unknown>;
  evidence: Array<{
    signal_id: string;
    stance: string;
    evidence_type: string;
    claim: string;
    confidence: number;
    last_seen_at: string;
  }>;
  transitions: Array<{
    from_status: string | null;
    to_status: string;
    actor: string;
    reason: string;
    created_at: string;
  }>;
};

export type Signal = {
  id: string;
  status: string;
  language: string;
  is_duplicate: boolean;
  duplicate_kind: string | null;
  processed_at: string | null;
  error: string | null;
  created_at: string;
};

export type Cluster = {
  id: string;
  title: string;
  summary: string;
  cluster_type: string;
  signal_count: number;
  source_count: number;
  evidence_type_count: number;
  corroboration_score: number;
  recurrence_score: number;
  velocity_30d: number;
};

export type Alert = {
  id: string;
  opportunity_id: string | null;
  alert_type: string;
  severity: string;
  status: string;
  title: string;
  message: string;
  created_at: string;
};

export type PortfolioItem = {
  id: string;
  opportunity_id: string;
  current_score: number;
  previous_score: number;
  score_velocity: number;
  pain_velocity: number;
  competition_velocity: number;
  market_timing_velocity: number;
  rank: number | null;
  previous_rank: number | null;
  state: string;
  reasons: string[];
  assessed_at: string;
};

export type ResearchCampaign = {
  id: string;
  opportunity_id: string;
  version: string;
  status: string;
  required_lane_count: number;
  completed_lane_count: number;
  failed_lane_count: number;
  coverage_score: number;
  cost_usd: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
};

export type BuildSpec = {
  id: string;
  opportunity_id: string;
  version: string;
  status: string;
  approved_by: string | null;
  created_at: string;
};

export type Metrics = Record<string, number>;

export type ApiResult<T> = {
  data: T;
  online: boolean;
  error?: string;
};

export async function getApi<T>(path: string, fallback: T): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) {
      return {
        data: fallback,
        online: false,
        error: `API returned ${response.status}`,
      };
    }
    return { data: (await response.json()) as T, online: true };
  } catch (error) {
    return {
      data: fallback,
      online: false,
      error: error instanceof Error ? error.message : "API unavailable",
    };
  }
}

export function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function timeAgo(value: string) {
  const difference = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(difference / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
