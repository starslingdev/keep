"use client";

import { useState } from "react";
import { Button, Card, TextInput } from "@tremor/react";
import { showErrorToast, showSuccessToast } from "@/shared/ui";
import Link from "next/link";

interface SignupResponse {
  tenant_id: string;
  organization_name: string;
  email: string;
  password: string;
  login_url: string;
  message: string;
}

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [orgName, setOrgName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [credentials, setCredentials] = useState<SignupResponse | null>(null);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email || !orgName) {
      showErrorToast("Please fill in all required fields");
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch("/api/public/signup", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          organization_name: orgName,
          first_name: firstName || undefined,
          last_name: lastName || undefined,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Signup failed");
      }

      const data: SignupResponse = await response.json();
      setCredentials(data);
      showSuccessToast("Account created successfully!");
    } catch (error: any) {
      console.error("Signup error:", error);
      showErrorToast(error.message || "Failed to create account");
    } finally {
      setIsLoading(false);
    }
  };

  if (credentials) {
    return (
      <div className="flex items-center justify-center min-h-screen p-4">
        <Card className="max-w-2xl w-full bg-slate-800/50 border-purple-500/20">
          <div className="space-y-6">
            <div className="text-center">
              <h1 className="text-3xl font-bold text-purple-400 mb-2">
                ✨ Welcome to Continuum
              </h1>
              <p className="text-slate-300">
                Your account has been created successfully
              </p>
            </div>

            <div className="bg-purple-900/30 border border-purple-500/30 rounded-lg p-4">
              <p className="text-sm font-semibold text-purple-300 mb-2">
                ⚠️ Important: Save Your Credentials
              </p>
              <p className="text-sm text-slate-300">
                Please save these credentials in a secure location. You won't be
                able to see the password again.
              </p>
            </div>

            <div className="space-y-3 bg-slate-900/50 p-4 rounded-lg border border-slate-700">
              <div>
                <p className="text-sm font-medium text-slate-400">Organization</p>
                <p className="font-mono text-sm text-slate-200">
                  {credentials.organization_name}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-400">Email</p>
                <p className="font-mono text-sm text-slate-200">{credentials.email}</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-400">
                  Temporary Password
                </p>
                <p className="font-mono text-sm bg-slate-800 text-purple-300 p-2 rounded border border-purple-500/30">
                  {credentials.password}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-400">Tenant ID</p>
                <p className="font-mono text-sm text-slate-500">
                  {credentials.tenant_id}
                </p>
              </div>
            </div>

            <div className="space-y-3">
              <Button
                size="lg"
                className="w-full bg-orange-600 hover:bg-orange-700"
                onClick={() => {
                  window.location.href = credentials.login_url;
                }}
              >
                Go to Login →
              </Button>
              <p className="text-xs text-center text-gray-500">
                Change your password after your first login
              </p>
            </div>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Hero Section */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="text-center mb-16">
          <h1 className="text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-400 mb-4">
            ✨ Continuum
          </h1>
          <p className="text-2xl font-semibold text-slate-200 mb-3">
            AI-Powered Incident Analysis
          </p>
          <p className="text-lg text-slate-400 max-w-3xl mx-auto">
            Automatically analyze incidents and generate Root Cause Analysis—accelerate your incident response.
          </p>
        </div>

        {/* Features Grid */}
        <div className="grid md:grid-cols-3 gap-8 mb-16">
          <Card className="text-center bg-slate-800/50 border-purple-500/20">
            <div className="text-4xl mb-4">🔍</div>
            <h3 className="text-lg font-semibold mb-2 text-purple-300">
              Automated Root Cause Analysis
            </h3>
            <p className="text-slate-400 text-sm">
              AI analyzes alert context, Sentry stacktraces, and error patterns
              to identify the root cause
            </p>
          </Card>

          <Card className="text-center bg-slate-800/50 border-purple-500/20">
            <div className="text-4xl mb-4">⚡</div>
            <h3 className="text-lg font-semibold mb-2 text-purple-300">
              Intelligent Insights
            </h3>
            <p className="text-slate-400 text-sm">
              Ranked hypotheses, evidence analysis, and actionable recommendations
              in seconds
            </p>
          </Card>

          <Card className="text-center bg-slate-800/50 border-purple-500/20">
            <div className="text-4xl mb-4">🚀</div>
            <h3 className="text-lg font-semibold mb-2 text-purple-300">
              Reduce MTTR by 10x
            </h3>
            <p className="text-slate-400 text-sm">
              From alert to actionable analysis in under 10 seconds. No manual investigation
              needed.
            </p>
          </Card>
        </div>

        {/* Signup Form */}
        <Card className="max-w-xl mx-auto bg-slate-800/70 border-purple-500/30">
          <div className="text-center mb-6">
            <h2 className="text-2xl font-bold mb-2 text-slate-100">Start Your Free Trial</h2>
            <p className="text-slate-400">
              No credit card required. AI analysis enabled by default.
            </p>
          </div>

          <form onSubmit={handleSignup} className="space-y-4">
            <div>
              <label className="text-sm font-medium text-slate-300 block mb-1">
                Work Email *
              </label>
              <TextInput
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-300 block mb-1">
                Organization Name *
              </label>
              <TextInput
                type="text"
                placeholder="Acme Inc"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-slate-300 block mb-1">
                  First Name
                </label>
                <TextInput
                  type="text"
                  placeholder="John"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-300 block mb-1">
                  Last Name
                </label>
                <TextInput
                  type="text"
                  placeholder="Doe"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                />
              </div>
            </div>

            <Button
              type="submit"
              size="lg"
              className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 border-0 text-white"
              loading={isLoading}
              disabled={isLoading}
            >
              Create Account
            </Button>

            <p className="text-xs text-center text-slate-500">
              By signing up, you agree to our Terms of Service and Privacy
              Policy
            </p>
          </form>

          <div className="mt-6 text-center">
            <p className="text-sm text-slate-400">
              Already have an account?{" "}
              <Link href="/signin" className="text-purple-400 hover:text-purple-300 font-medium">
                Sign in
              </Link>
            </p>
          </div>
        </Card>

        {/* Social Proof */}
        <div className="text-center mt-16">
          <p className="text-slate-500 mb-4">Trusted by engineering teams</p>
        </div>

        {/* How It Works */}
        <div className="mt-24">
          <h2 className="text-3xl font-bold text-center mb-12 text-slate-100">
            How It Works
          </h2>
          <div className="grid md:grid-cols-4 gap-6">
            <div className="text-center">
              <div className="bg-purple-900/50 border border-purple-500/30 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-4 text-xl font-bold text-purple-300">
                1
              </div>
              <h3 className="font-semibold mb-2 text-slate-200">Alert Triggers</h3>
              <p className="text-sm text-slate-400">
                Your monitoring tool sends an alert to Continuum
              </p>
            </div>

            <div className="text-center">
              <div className="bg-purple-900/50 border border-purple-500/30 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-4 text-xl font-bold text-purple-300">
                2
              </div>
              <h3 className="font-semibold mb-2 text-slate-200">Click Button</h3>
              <p className="text-sm text-slate-400">
                Click "AI: Analyze Root Cause" in Continuum UI
              </p>
            </div>

            <div className="text-center">
              <div className="bg-purple-900/50 border border-purple-500/30 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-4 text-xl font-bold text-purple-300">
                3
              </div>
              <h3 className="font-semibold mb-2 text-slate-200">AI Analyzes</h3>
              <p className="text-sm text-slate-400">
                Fetches context, Sentry data, generates comprehensive RCA
              </p>
            </div>

            <div className="text-center">
              <div className="bg-purple-900/50 border border-purple-500/30 rounded-full w-12 h-12 flex items-center justify-center mx-auto mb-4 text-xl font-bold text-purple-300">
                4
              </div>
              <h3 className="font-semibold mb-2 text-slate-200">Results Ready</h3>
              <p className="text-sm text-slate-400">
                Detailed RCA with ranked hypotheses and fix recommendations
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-24 text-center text-slate-500 text-sm">
          <p>
            Powered by{" "}
            <Link
              href="https://keephq.dev"
              className="text-purple-400 hover:text-purple-300"
            >
              Keep
            </Link>{" "}
            - The open-source AIOps platform
          </p>
        </footer>
      </div>
    </div>
  );
}

