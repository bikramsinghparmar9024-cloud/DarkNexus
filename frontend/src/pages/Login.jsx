import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, Lock, User, ArrowRight, Loader2, Wifi, WifiOff } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { describeApiError, API_BASE_URL } from '../api/client';

/*
 * Sign-in.
 *
 * The fields used to arrive pre-filled with admin_punjab / PunjabPolice@2026,
 * the same pair was printed beneath the form, and an "offline mode" accepted
 * them without the backend. None of that survives: there is no credential in
 * this application, and no session without the server.
 */

// Resolved once in api/client.js. Repeating the fallback here is how
// this file kept pointing at 127.0.0.1 after the shared client was
// fixed for same-origin deployment.
const API_BASE = API_BASE_URL;

export const Login = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [backendReachable, setBackendReachable] = useState(null);
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (isAuthenticated) navigate('/overview', { replace: true });
  }, [isAuthenticated, navigate]);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(4000) })
      .then((res) => { if (!cancelled) setBackendReachable(res.ok); })
      .catch(() => { if (!cancelled) setBackendReachable(false); });
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
      navigate('/overview', { replace: true });
    } catch (err) {
      setError(describeApiError(err).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex" style={{ background: 'var(--surface-page)' }}>
      {/* Identity panel. Uses the navigation rail colour so the application is
          recognisable before the user is inside it. */}
      <div
        className="hidden lg:flex w-[46%] flex-col justify-between p-12"
        style={{ background: 'var(--rail-bg)' }}
      >
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center"
               style={{ background: 'rgba(255,255,255,0.08)' }}>
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div className="leading-tight">
            <div className="text-[10px] uppercase tracking-[0.12em]" style={{ color: 'var(--rail-muted)' }}>
              Government of India
            </div>
            <div className="text-[14px] font-semibold text-white">Chandigarh Police</div>
          </div>
        </div>

        <div>
          <h1 className="text-[38px] font-bold text-white leading-tight tracking-tight">DarkNexus</h1>
          <p className="text-[15px] mt-2" style={{ color: 'var(--rail-text)' }}>
            Drug Intelligence &amp; Evidence System
          </p>
          <div className="mt-8 space-y-3 max-w-sm">
            {[
              'Continuous collection across surface web, dark web and encrypted messaging',
              'SHA-256 chain of custody on every record, attributed to the accessing officer',
              'Correlation that states its confidence and declines to guess',
            ].map((line) => (
              <div key={line} className="flex items-start gap-2.5">
                <div className="w-1 h-1 rounded-full mt-2 shrink-0" style={{ background: '#38bdf8' }} />
                <p className="text-[13px] leading-relaxed" style={{ color: 'var(--rail-text)' }}>{line}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="text-[11px]" style={{ color: 'var(--rail-muted)' }}>
          Authorised law enforcement personnel only · Access is monitored and logged
        </p>
      </div>

      {/* Credential panel */}
      <div className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-[380px]">
          <div className="lg:hidden flex items-center gap-2.5 mb-6">
            <div className="w-9 h-9 rounded-lg flex items-center justify-center"
                 style={{ background: 'var(--rail-bg)' }}>
              <ShieldCheck className="w-4.5 h-4.5 text-white" />
            </div>
            <div className="leading-tight">
              <div className="text-[15px] font-bold" style={{ color: 'var(--text-primary)' }}>DarkNexus</div>
              <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Chandigarh Police</div>
            </div>
          </div>

          <div className="mb-6">
            <h2 className="text-[20px] font-semibold" style={{ color: 'var(--text-primary)' }}>
              Sign in
            </h2>
            <p className="text-[13px] mt-1" style={{ color: 'var(--text-secondary)' }}>
              Use the credentials issued to your badge.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-3.5">
            <div>
              <label className="label block mb-1.5">Badge ID / Username</label>
              <div className="relative">
                <User className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: 'var(--text-muted)' }} />
                <input
                  className="input pl-8"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin_punjab"
                />
              </div>
            </div>

            <div>
              <label className="label block mb-1.5">Password</label>
              <div className="relative">
                <Lock className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: 'var(--text-muted)' }} />
                <input
                  className="input pl-8"
                  type="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
            </div>

            {error && (
              <div className="rounded-lg px-3 py-2 text-[12px]"
                   style={{
                     background: 'var(--risk-high-bg)',
                     color: 'var(--risk-high-text)',
                     border: '1px solid var(--risk-high-border)',
                   }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary w-full justify-center py-2.5"
              disabled={loading || !username || !password || backendReachable === false}
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              {loading ? 'Verifying…' : 'Sign in'}
              {!loading && <ArrowRight className="w-3.5 h-3.5" />}
            </button>
          </form>

          <div className="mt-6 pt-5 space-y-2" style={{ borderTop: '1px solid var(--border)' }}>
            {backendReachable === false && (
              <div className="flex items-center gap-1.5 text-[12px]" style={{ color: 'var(--risk-high-text)' }}>
                <WifiOff className="w-3.5 h-3.5" />
                Backend unreachable — sign-in unavailable until it is running.
              </div>
            )}
            {backendReachable === true && (
              <div className="flex items-center gap-1.5 text-[12px]" style={{ color: 'var(--status-active)' }}>
                <Wifi className="w-3.5 h-3.5" /> Backend connected
              </div>
            )}
            <p className="text-[11px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              On first start the server prints a generated administrator password
              to its console. No credentials are stored in this application.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
