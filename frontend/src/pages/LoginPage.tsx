import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError } from "@/lib/api";

interface LocationState {
  from?: { pathname: string };
}

export function LoginPage() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LocationState | null)?.from?.pathname ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!loading && user) {
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Could not sign in. Please try again.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-full grid lg:grid-cols-2">
      {/* Left: brand panel */}
      <div className="hidden lg:flex flex-col justify-between p-12 bg-aspora-700 text-white relative overflow-hidden">
        <div className="relative z-10">
          <img
            src="/static/brand/aspora-wordmark.png"
            alt="Aspora"
            className="h-9 brightness-0 invert"
          />
        </div>
        <div className="relative z-10 max-w-md space-y-4">
          <h1 className="text-3xl font-semibold leading-tight">
            Compliance OS for fintech & remittance.
          </h1>
          <p className="text-aspora-100/90">
            Every obligation across every entity, on one calendar.
            Built for global teams that file in many places at once.
          </p>
        </div>
        <div className="relative z-10 text-aspora-200 text-xs">
          © {new Date().getFullYear()} Aspora · All rights reserved
        </div>

        {/* Decorative blob */}
        <div className="absolute -bottom-32 -right-24 h-96 w-96 rounded-full bg-aspora-500/40 blur-3xl" />
        <div className="absolute -top-24 -left-24 h-72 w-72 rounded-full bg-aspora-400/30 blur-3xl" />
      </div>

      {/* Right: form */}
      <div className="flex items-center justify-center p-6 sm:p-12 bg-background">
        <div className="w-full max-w-sm space-y-8">
          <div className="lg:hidden flex justify-center">
            <img src="/static/brand/aspora-wordmark.png" alt="Aspora" className="h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold">Sign in</h2>
            <p className="text-sm text-muted-foreground">
              Welcome back. Sign in with your Aspora account.
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
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium">
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
                {error}
              </div>
            )}

            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          <div className="text-xs text-muted-foreground">
            Trouble signing in? Ask your Aspora admin to reset your password
            via the <code className="bg-secondary px-1 py-0.5 rounded">compliance-agent create-user</code> CLI.
          </div>
        </div>
      </div>
    </div>
  );
}
