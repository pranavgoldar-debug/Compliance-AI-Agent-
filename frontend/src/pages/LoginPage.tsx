import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, api, apiUrl } from "@/lib/api";

interface LocationState {
  from?: { pathname: string };
}

// Errors the Google OAuth callback redirects back with (?error=…).
const GOOGLE_ERRORS: Record<string, string> = {
  google_no_account:
    "No Finance Compliance OS account for that Google email. Ask your admin for access.",
  google_domain: "Use your @aspora.com Google account to sign in.",
  google_unverified: "That Google email isn't verified.",
  google_unconfigured: "Google sign-in isn't enabled.",
  google_state: "Sign-in session expired. Please try again.",
  google_failed: "Could not sign in with Google. Please try again.",
};

function GoogleIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.05l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}

export function LoginPage() {
  const { user, login, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as LocationState | null)?.from?.pathname ?? "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Whether Google sign-in is configured on the server (GOOGLE_CLIENT_ID/SECRET).
  const [googleEnabled, setGoogleEnabled] = useState(false);

  useEffect(() => {
    api
      .get<{ google: boolean }>("/api/auth/providers")
      .then((p) => setGoogleEnabled(!!p.google))
      .catch(() => setGoogleEnabled(false));
  }, []);

  // Surface errors the Google OAuth callback redirected back with.
  useEffect(() => {
    const e = new URLSearchParams(location.search).get("error");
    if (e) setError(GOOGLE_ERRORS[e] ?? "Could not sign in. Please try again.");
  }, [location.search]);

  if (!loading && user) {
    return <Navigate to={from} replace />;
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      // Lowercase + trim mirror the backend's normalization. Belt + braces:
      // copy-pasting creds from Slack often grabs a trailing space, and DB
      // stores emails lowercased so a capital first letter would 401.
      await login(email.trim().toLowerCase(), password);
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
        <div className="relative z-10 inline-flex items-center gap-2.5">
          <img
            src="/static/brand/aspora-mark.svg"
            alt=""
            aria-hidden="true"
            className="h-9 w-9"
          />
          <span className="text-2xl font-semibold tracking-tight">
            Finance Compliance OS
          </span>
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
          © {new Date().getFullYear()} Finance Compliance OS · All rights reserved
        </div>

        {/* Decorative blob */}
        <div className="absolute -bottom-32 -right-24 h-96 w-96 rounded-full bg-aspora-500/40 blur-3xl" />
        <div className="absolute -top-24 -left-24 h-72 w-72 rounded-full bg-aspora-400/30 blur-3xl" />
      </div>

      {/* Right: form */}
      <div className="flex items-center justify-center p-6 sm:p-12 bg-background">
        <div className="w-full max-w-sm space-y-8">
          <div className="lg:hidden flex items-center justify-center gap-2">
            <img src="/static/brand/aspora-mark.svg" alt="" aria-hidden="true" className="h-8 w-8" />
            <span className="text-xl font-semibold tracking-tight">
              Finance Compliance OS
            </span>
          </div>
          <div className="space-y-2">
            <h2 className="text-2xl font-semibold">Sign in</h2>
            <p className="text-sm text-muted-foreground">
              Welcome back. Sign in with your Finance Compliance OS account.
            </p>
          </div>

          {googleEnabled && (
            <>
              <button
                type="button"
                onClick={() => {
                  window.location.href = apiUrl("/api/auth/google/start");
                }}
                className="w-full inline-flex items-center justify-center gap-2.5 rounded-md border border-input bg-background px-4 py-2.5 text-sm font-medium hover:bg-secondary transition-colors"
              >
                <GoogleIcon className="h-4 w-4" />
                Continue with Google
              </button>
              <div className="relative">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center">
                  <span className="bg-background px-2 text-xs text-muted-foreground">or</span>
                </div>
              </div>
            </>
          )}

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
              <div className="relative">
                <Input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((s) => !s)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-secondary"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  tabIndex={-1}
                >
                  {showPassword ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </button>
              </div>
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

          <div className="text-xs text-muted-foreground flex items-center justify-between">
            <Link to="/forgot-password" className="text-aspora-700 hover:underline">
              Forgot password?
            </Link>
            <span>Need access? Ask your admin.</span>
          </div>
        </div>
      </div>
    </div>
  );
}
