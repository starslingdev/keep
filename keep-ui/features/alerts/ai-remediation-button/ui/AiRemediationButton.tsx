"use client";

import { useState, useEffect, useCallback } from "react";
import { Button } from "@tremor/react";
import { Link } from "@/components/ui";
import { showErrorToast, showSuccessToast } from "@/shared/ui";
import { useApi } from "@/shared/lib/hooks/useApi";
import { triggerAiRemediation } from "../api/triggerAiRemediation";

export interface AiRemediationButtonProps {
  alertId?: string;
  incidentId?: string;
  existingRemediation?: {
    ai_remediation_status?: "pending" | "success" | "failed";
    ai_pr_url?: string;
    ai_rca_summary?: string;
    ai_rca_full_report?: string;
    ai_error_message?: string;
  };
  onRemediationStarted?: () => void;
  onRemediationComplete?: () => void;
}

interface RemediationState {
  status: "idle" | "pending" | "success" | "failed";
  summary?: string;
  fullReport?: string;
  prUrl?: string;
  errorMessage?: string;
}

export function AiRemediationButton({
  alertId,
  incidentId,
  existingRemediation,
  onRemediationStarted,
  onRemediationComplete,
}: AiRemediationButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [showFullReport, setShowFullReport] = useState(false);
  const [state, setState] = useState<RemediationState>(() => {
    // Initialize from existing remediation
    if (existingRemediation?.ai_remediation_status === "success") {
      return {
        status: "success",
        summary: existingRemediation.ai_rca_summary,
        fullReport: existingRemediation.ai_rca_full_report,
        prUrl: existingRemediation.ai_pr_url,
      };
    }
    if (existingRemediation?.ai_remediation_status === "failed") {
      return {
        status: "failed",
        errorMessage: existingRemediation.ai_error_message,
      };
    }
    if (existingRemediation?.ai_remediation_status === "pending") {
      return { status: "pending" };
    }
    return { status: "idle" };
  });
  
  const api = useApi();

  // Poll for updates when status is pending
  useEffect(() => {
    if (state.status !== "pending" || !alertId) {
      return;
    }

    const checkStatus = async () => {
      try {
        // Use the dedicated AI remediation status endpoint
        const response = await api.get<{
          status: string;
          ai_remediation_status?: string;
          ai_rca_summary?: string;
          ai_rca_full_report?: string;
          ai_pr_url?: string;
          ai_error_message?: string;
        }>(`/ai/remediation/status/${alertId}`);
        
        if (response.ai_remediation_status === "success") {
          setState({
            status: "success",
            summary: response.ai_rca_summary,
            fullReport: response.ai_rca_full_report,
            prUrl: response.ai_pr_url,
          });
          showSuccessToast("Root cause analysis complete!");
          if (onRemediationComplete) {
            onRemediationComplete();
          }
          if (onRemediationStarted) {
            onRemediationStarted(); // Refresh parent data
          }
        } else if (response.ai_remediation_status === "failed") {
          setState({
            status: "failed",
            errorMessage: response.ai_error_message || "Analysis failed",
          });
          showErrorToast("Root cause analysis failed");
          if (onRemediationStarted) {
            onRemediationStarted(); // Refresh parent data
          }
        }
        // If still pending, keep polling
      } catch (error) {
        console.error("Failed to check remediation status:", error);
      }
    };

    // Poll every 2 seconds
    const interval = setInterval(checkStatus, 2000);
    
    // Also check immediately
    checkStatus();

    return () => clearInterval(interval);
  }, [state.status, alertId, api, onRemediationComplete, onRemediationStarted]);

  // Update state when props change (e.g., after parent refresh)
  useEffect(() => {
    if (existingRemediation?.ai_remediation_status === "success" && state.status !== "success") {
      setState({
        status: "success",
        summary: existingRemediation.ai_rca_summary,
        fullReport: existingRemediation.ai_rca_full_report,
        prUrl: existingRemediation.ai_pr_url,
      });
    } else if (existingRemediation?.ai_remediation_status === "failed" && state.status !== "failed") {
      setState({
        status: "failed",
        errorMessage: existingRemediation.ai_error_message,
      });
    }
  }, [existingRemediation, state.status]);

  const handleClick = useCallback(async () => {
    if (!alertId && !incidentId) {
      showErrorToast("No alert or incident ID provided");
      return;
    }

    if (!api.isReady()) {
      showErrorToast("API not ready. Please try again.");
      return;
    }

    setIsLoading(true);

    try {
      const response = await triggerAiRemediation(api, {
        alertId,
        incidentId,
      });

      // Immediately show pending state
      setState({ status: "pending" });

      showSuccessToast(
        `AI remediation started! ${response.message}`
      );

      // Notify parent component
      if (onRemediationStarted) {
        onRemediationStarted();
      }
    } catch (error: any) {
      console.error("Failed to trigger AI remediation:", error);
      
      const errorMessage =
        error.message ||
        error.detail ||
        "Failed to start AI remediation. Please try again.";
      
      showErrorToast(errorMessage);
    } finally {
      setIsLoading(false);
    }
  }, [alertId, incidentId, api, onRemediationStarted]);

  // Show RCA results if successful
  if (state.status === "success") {
    return (
      <div className="flex flex-col gap-2">
        <div className="bg-green-50 border border-green-200 rounded p-3">
          <p className="text-xs font-semibold text-green-800 mb-1">
            ✓ Root Cause Analysis Complete
          </p>
          {state.summary && (
            <p className="text-sm text-gray-700 mb-2">
              {state.summary}
            </p>
          )}
          {state.prUrl && (
            <Link
              href={state.prUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 font-medium text-sm block mb-2"
            >
              View GitHub PR →
            </Link>
          )}
          {state.fullReport && (
            <div className="mt-2">
              <Button
                size="xs"
                variant="light"
                onClick={() => setShowFullReport(!showFullReport)}
              >
                {showFullReport ? "Hide Full Report" : "Show Full Report"}
              </Button>
              {showFullReport && (
                <div className="mt-2 bg-white border border-gray-200 rounded p-3 max-h-96 overflow-y-auto">
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono">
                    {state.fullReport}
                  </pre>
                </div>
              )}
            </div>
          )}
        </div>
        <Button
          size="xs"
          variant="secondary"
          onClick={handleClick}
          loading={isLoading}
          disabled={isLoading}
        >
          Re-run Analysis
        </Button>
      </div>
    );
  }

  // Show error state if failed
  if (state.status === "failed") {
    return (
      <div className="flex flex-col gap-2">
        <div className="bg-red-50 border border-red-200 rounded p-3">
          <p className="text-sm text-red-600">
            ❌ AI remediation failed: {state.errorMessage || "Unknown error"}
          </p>
        </div>
        <Button
          size="xs"
          variant="secondary"
          onClick={handleClick}
          loading={isLoading}
          disabled={isLoading}
        >
          Retry Analysis
        </Button>
      </div>
    );
  }

  // Show pending state if in progress
  if (state.status === "pending") {
    return (
      <div className="flex flex-col gap-2">
        <div className="bg-blue-50 border border-blue-200 rounded p-3 flex items-center gap-2">
          <div className="animate-spin h-4 w-4 border-2 border-blue-600 border-t-transparent rounded-full" />
          <p className="text-sm text-blue-700">
            Analyzing root cause... This may take a minute.
          </p>
        </div>
      </div>
    );
  }

  // Default: show trigger button
  return (
    <Button
      size="xs"
      onClick={handleClick}
      loading={isLoading}
      disabled={isLoading}
      className="bg-blue-600 hover:bg-blue-700 text-white"
    >
      🤖 AI: Analyze Root Cause
    </Button>
  );
}
