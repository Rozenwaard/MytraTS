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

export interface DashboardOverview {
  total: number;
  psk: number;
  rle: number;
  plan: number;
  unplan: number;
  completed: number;
  uncompleted: number;
  with_errors: number;
  without_errors: number;
  cost: number;
}
