export interface DashboardError {
  label: string;
  count: number;
}

export interface DashboardSummary {
  total_rows: number;
  with_errors: number;
  billed_count: number;
  unbilled_count: number;
  total_errors: number;
  errors: DashboardError[];
}
