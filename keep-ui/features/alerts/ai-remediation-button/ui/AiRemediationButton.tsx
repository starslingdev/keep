"use client";

import { useState } from "react";
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
    ai_error_message?: string;
  };
  onRemediationStarted?: () => void;
}

export function AiRemediationButton({
  alertId,
  incidentId,
  existingRemediation,
  onRemediationStarted,
}: AiRemediationButtonProps) {
  const [isLoading, setIsLoading] = useState(false);
  const api = useApi();

  const handleClick = async () => {
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
  };

  // Show RCA results if available and successful
  if (existingRemediation?.ai_remediation_status === "success") {
    return (
      <div className="flex flex-col gap-2">
        {existingRemediation.ai_pr_url && (
          <Link
            href={existingRemediation.ai_pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 font-medium text-sm"
          >
            View GitHub PR →
          </Link>
        )}
        {existingRemediation.ai_rca_summary && (
          <div className="bg-green-50 border border-green-200 rounded p-3">
            <p className="text-xs font-semibold text-green-800 mb-1">
              ✓ Root Cause Analysis Complete
            </p>
            <p className="text-sm text-gray-700">
              {existingRemediation.ai_rca_summary}
            </p>
          </div>
        )}
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
  if (existingRemediation?.ai_remediation_status === "failed") {
    return (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-red-600">
          AI remediation failed: {existingRemediation.ai_error_message || "Unknown error"}
        </p>
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
  if (existingRemediation?.ai_remediation_status === "pending") {
    return (
      <Button
        size="xs"
        variant="secondary"
        disabled
        loading
      >
        Analyzing...
      </Button>
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

