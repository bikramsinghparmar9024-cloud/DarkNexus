import React, { useState } from 'react';
import { ShieldAlert, KeyRound, Loader2 } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';
import { describeApiError } from '../api/client';

/*
 * Shown when an account is still on the password generated at first start.
 *
 * The initial password is printed once to the server console and never stored
 * in readable form. Until it is replaced the account is blocked from the rest
 * of the application, so a deployment cannot sit indefinitely on a credential
 * that was echoed into a log file.
 */
export const ChangePasswordGate = () => {
  const { user, changePassword, logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const tooShort = newPassword.length > 0 && newPassword.length < 12;
  const mismatch = confirmPassword.length > 0 && newPassword !== confirmPassword;
  const canSubmit = currentPassword && newPassword.length >= 12
    && newPassword === confirmPassword && !busy;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      await changePassword(currentPassword, newPassword);
    } catch (err) {
      setError(describeApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full flex items-center justify-center p-6" style={{ background: 'var(--surface-page)' }}>
      <div className="w-full max-w-md">
        <div className="card p-6 space-y-5" style={{ borderLeft: '3px solid var(--risk-medium-text)' }}>
          <div className="flex items-start gap-3">
            <ShieldAlert className="w-5 h-5 shrink-0 mt-0.5" style={{ color: 'var(--risk-medium-text)' }} />
            <div>
              <h1 className="text-[17px] font-semibold" style={{ color: 'var(--text-primary)' }}>Set a new password</h1>
              <p className="text-[13px] mt-1 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                This account is still using the password generated at first start,
                which was printed to the server console. Replace it before continuing.
              </p>
            </div>
          </div>

          {user?.username && (
            <div className="text-[12px] mono py-2" style={{ color: 'var(--text-muted)', borderTop: '1px solid var(--border)', borderBottom: '1px solid var(--border)' }}>
              Signed in as <span style={{ color: 'var(--accent)' }}>{user.username}</span>
              {user.badge_number ? ` · ${user.badge_number}` : ''}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className="label block mb-1">
                Current password
              </label>
              <input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                className="input"
              />
            </div>

            <div>
              <label className="label block mb-1">
                New password
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="input"
              />
              <p className="text-[11px] mt-1" style={{ color: tooShort ? 'var(--risk-medium-text)' : 'var(--text-muted)' }}>
                At least 12 characters.
              </p>
            </div>

            <div>
              <label className="label block mb-1">
                Confirm new password
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="input"
              />
              {mismatch && (
                <p className="text-[11px] mt-1" style={{ color: 'var(--risk-medium-text)' }}>Passwords do not match.</p>
              )}
            </div>

            {error && (
              <div className="text-[12px] rounded-lg px-3 py-2" style={{ background: 'var(--risk-high-bg)', color: 'var(--risk-high-text)', border: '1px solid var(--risk-high-border)' }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={!canSubmit}
              className="btn btn-primary w-full justify-center py-2.5"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <KeyRound className="w-4 h-4" />}
              {busy ? 'Updating…' : 'Set new password'}
            </button>
          </form>

          <button
            onClick={logout}
            className="btn btn-ghost w-full justify-center text-[12px]"
          >
            Sign out instead
          </button>
        </div>
      </div>
    </div>
  );
};
