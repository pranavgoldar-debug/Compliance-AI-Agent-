// /forgot-password — enter email, kick off the reset flow.
//
// The backend always returns ok:true regardless of whether the email exists
// (account enumeration guard), so the UI shows the same confirmation either
// way. In dev (no SMTP), the response carries dev_reset_url which we surface
// as a "copy link" affordance for the admin.

import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Copy, Loader2, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";


interface ForgotResponse {
  ok: boolean;
  dev_reset_url: string | null;
}


export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [devUrl, setDevUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await api.post<ForgotResponse>("/api/auth/forgot-password", {
        email: email.trim().toLowerCase(),
      });
      setDevUrl(res.dev_reset_url);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not send reset email.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-full grid lg:grid-cols-2">
      <div className="hidden lg:flex flex-col justify-between p-12 bg-aspora-700 text-white relative overflow-hidden">
        <img
          src="/static/brand/aspora-wordmark.png"
          alt="Aspora"
          className="h-9 brightness-0 invert relative z-10"
        />
        <div className="relative z-10 max-w-md space-y-4">
          <h1 className="text-3xl font-semibold leading-tight">
            Reset your password.
          </h1>
          <p className="text-aspora-100/90">
            We'll email a one-time link. The link expires in an hour.
          </p>
        </div>
        <div className="relative z-10 text-aspora-200 text-xs">
          © {new Date().getFullYear()} Aspora · All rights reserved
        </div>
        <div className="absolute -bottom-32 -right-24 h-96 w-96 rounded-full bg-aspora-500/40 blur-3xl" />
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12 bg-background">
        <div className="w-full max-w-sm space-y-6">
          <Link
            to="/login"
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to sign in
          </Link>

          {!done ? (
            <>
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold">Forgot password?</h2>
                <p className="text-sm text-muted-foreground">
                  Enter the email on your Aspora account. We'll send a reset link.
                </p>
              </div>

              <form className="space-y-4" onSubmit={onSubmit}>
                <div className="space-y-2">
                  <label htmlFor="email" className="text-sm font-medium">
                    Email
                  </label>
                  <Input
                    id="email"
                    type="email"
                    autoComplete="email"
                    required
                    placeholder="you@aspora.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>

                {error && (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                    {error}
                  </div>
                )}

                <Button type="submit" className="w-full" disabled={submitting || !email}>
                  {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                  Send reset link
                </Button>
              </form>
            </>
          ) : (
            <div className="space-y-4">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
                <div className="font-semibold">Check your inbox</div>
                <p className="mt-1">
                  If an Aspora account exists for <strong>{email}</strong>, we just sent a reset
                  link. It expires in an hour.
                </p>
              </div>

              {devUrl && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm">
                  <div className="font-semibold text-amber-900">Dev mode — SMTP not configured</div>
                  <p className="text-amber-900/90 mt-1">
                    Server has no SMTP creds. Reset link is below — copy and share it manually.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <Input value={devUrl} readOnly className="font-mono text-xs" />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => {
                        navigator.clipboard.writeText(devUrl).then(() => {
                          setCopied(true);
                          setTimeout(() => setCopied(false), 1500);
                        });
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {copied ? "Copied" : "Copy"}
                    </Button>
                  </div>
                </div>
              )}

              <Link to="/login" className="text-sm text-aspora-700 hover:underline">
                Back to sign in
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
