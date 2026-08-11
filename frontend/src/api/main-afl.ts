export interface MainAflRow {
  task_number: string | null;
  task_source: string | null;
  task_type: string | null;
  work_type_in_task: string | null;
  address: string | null;
  municipal_district: string | null;
  house_type: string | null;
  personal_account: string | null;
  service_object_type: string | null;
  subscriber_name: string | null;
  meter_installation_place: string | null;
  meter_status: string | null;
  meter_ownership: string | null;
  violations: string | null;
  comment: string | null;
  executor: string | null;
  visit_reason: string | null;
  customer: string | null;
  task_output: string | null;
  task_report: string | null;
  grid: string | null;
  done_day: string | null;
  reestr_number: string | null;
  reestr_date: string | null;
}

export interface MainAflResponse {
  rows: MainAflRow[];
  total: number;
  page: number;
  per_page: number;
}

export interface MainAflParams {
  page?: number;
  per_page?: number;
  sort?: string;
  order?: string;
  search?: string;
  customer?: string;
  task_report?: string;
  executor_org?: string;
  executor_filter?: string;
  only_completed?: boolean;
  only_without_reestr?: boolean;
}
