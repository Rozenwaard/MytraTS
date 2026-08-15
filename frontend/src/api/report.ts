export interface ReportCheckRow {
  task_number: string | null;
  address: string | null;
  subscriber_name: string | null;
  meter_serial_number: string | null;
  work_type: string | null;
  work_result: string | null;
  executor: string | null;
  done_day: string | null;
  errors: string[];
  error_count: number;
}

export interface ReportCheckResponse {
  total: number;
  with_errors: number;
  rows: ReportCheckRow[];
}
