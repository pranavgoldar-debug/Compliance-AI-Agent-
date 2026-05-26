// /reset-password?token=... — enter new password, finish the reset flow.

import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";


export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) {
      setError("Missing or invalid reset link.");
      return;
    }
    if (newPassword.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }
    if (newPassword !== confirm) {
      setError("Passwords don't match.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.post("/api/auth/reset-password", {
        token,
        new_password: newPassword,
      });
      setDone(true);
      setTimeout(() => navigate("/login", { replace: true }), 2000);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reset password.");
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
            Set a new password.
          </h1>
          <p className="text-aspora-100/90">
            Pick something you'll remember. Min 6 characters.
          </p>
        </div>
        <div className="relative z-10 text-aspora-200 text-xs">
          © {new Date().getFullYear()} Aspora · All rights reserved
        </div>
        <div className="absolute -bottom-32 -right-24 h-96 w-96 rounded-full bg-aspora-500/40 blur-3xl" />
      </div>

      <div className="flex items-center justify-center p-6 sm:p-12 bg-background">
        <div className="w-full max-w-sm space-y-6">
          {!done ? (
            <>
              <div className="space-y-2">
                <h2 className="text-2xl font-semibold flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-aspora-700" />
                  Reset password
                </h2>
                <p className="text-sm text-muted-foreground">
                  Enter a new password for your Aspora account.
                </p>
              </div>

              <form className="space-y-4" onSubmit={onSubmit}>
                <div className="space-y-2">
                  <label htmlFor="new" className="text-sm font-medium">
                    New password
                  </label>
                  <Input
                    id="new"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="confirm" className="text-sm font-medium">
                    Confirm password
                  </label>
                  <Input
                    id="confirm"
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                  />
                </div>

                {error && (
                  <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                    {error}
                  </div>
                )}

                <Button
                  type="submit"
                  className="w-full"
                  disabled={submitting || !newPassword || !confirm}
                >
                  {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
                  Set new password
                </Button>
              </form>

              <div className="text-xs text-muted-foreground">
                Link not working? Request a new one from{" "}
                <Link to="/forgot-password" className="text-aspora-700 hover:underline">
                  Forgot password
                </Link>
                .
              </div>
            </>
          ) : (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-sm text-emerald-800 flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 shrink-0 mt-0.5" />
              <div>
                <div className="font-semibold">Password updated</div>
                <p className="mt-1">Redirecting to sign in…</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
