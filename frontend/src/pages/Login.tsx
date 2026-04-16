import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Mail, Lock, ArrowRight } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { ApiError } from "@/api";
import Input from "@/components/Input";
import Button from "@/components/Button";

export default function Login() {
  const { user, loading: authLoading, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (authLoading) return null;
  if (user) return <Navigate to="/" replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Invalid email or password" : err.detail);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-bg-base px-4">
      <div className="w-full max-w-[420px] bg-bg-surface border border-border rounded-lg p-10">
        {/* Logo */}
        <div className="mb-8">
          <div className="flex items-center gap-1.5">
            <span className="text-2xl font-bold text-text-primary">insec</span>
            <span className="text-2xl font-bold text-accent-success">.</span>
            <span className="text-2xl font-bold text-text-primary">ml</span>
          </div>
          <p className="text-sm text-text-secondary mt-2">
            Sign in to the instructor platform
          </p>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <Input
            label="Email"
            type="email"
            placeholder="instructor@insec.ml"
            icon={<Mail />}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
          <Input
            label="Password"
            type="password"
            placeholder="••••••••"
            icon={<Lock />}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <Button
            type="submit"
            variant="primary"
            loading={loading}
            className="w-full"
          >
            Sign in
            <ArrowRight className="h-4 w-4" />
          </Button>
        </form>
      </div>

      <p className="mt-8 text-xs text-text-muted">
        &copy; insec.ml &mdash; instructor access only
      </p>
    </div>
  );
}
