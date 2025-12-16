import { ApiClient } from "@/shared/api/ApiClient";

export interface TriggerAiRemediationRequest {
  alertId?: string;
  incidentId?: string;
}

export interface TriggerAiRemediationResponse {
  job_id: string;
  status: "enqueued" | "processing";
  message: string;
}

export async function triggerAiRemediation(
  api: ApiClient,
  request: TriggerAiRemediationRequest
): Promise<TriggerAiRemediationResponse> {
  // Convert to snake_case for backend
  const payload = {
    alert_id: request.alertId,
    incident_id: request.incidentId,
  };

  return api.post<TriggerAiRemediationResponse>("/ai/remediate", payload);
}
