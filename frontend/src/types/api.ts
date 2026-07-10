/** Shared API response shape for the backend health endpoint. */
export interface HealthResponse {
  status: string;
  environment: string;
}
