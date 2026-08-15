export interface DashboardError {
  label: string;
  count: number;
}

export interface DashboardSummary {
  total_with_errors: number;
  total_errors: number;
  errors: DashboardError[];
}
