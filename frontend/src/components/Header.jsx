import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Bell, ChevronDown, LogOut, ShieldCheck, Moon, Sun } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

/*
 * Application header.
 *
 * The identity chip shows the badge number the server returned, not a value
 * baked into the client. It previously displayed PB-CID-8821 unconditionally,
 * including for a session that had never signed in.
 */

const THEME_KEY = 'ui_theme';

export const Header = ({ title }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || 'light');
  const menuRef = useRef(null);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const onClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuOpen(false);
    };
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const initials = (user?.username || '?')
    .replace(/[^a-zA-Z]/g, ' ')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('') || '?';

  const submitSearch = (e) => {
    e.preventDefault();
    const q = query.trim();
    if (q) navigate(`/intelligence?q=${encodeURIComponent(q)}`);
  };

  return (
    <header
      className="h-14 shrink-0 flex items-center gap-4 px-4"
      style={{ background: 'var(--surface-card)', borderBottom: '1px solid var(--border)' }}
    >
      <div className="flex items-center gap-2.5 shrink-0">
        <div className="w-8 h-8 rounded-lg flex items-center justify-center"
             style={{ background: 'var(--rail-bg)', color: '#fff' }}>
          <ShieldCheck className="w-4.5 h-4.5" />
        </div>
        <div className="leading-tight hidden sm:block">
          <div className="text-[9px] uppercase tracking-[0.1em]" style={{ color: 'var(--text-muted)' }}>
            Government of India
          </div>
          <div className="text-[12px] font-semibold" style={{ color: 'var(--text-primary)' }}>
            Chandigarh Police
          </div>
        </div>
      </div>

      <div className="hidden lg:block text-center flex-1 min-w-0">
        <div className="text-[15px] font-bold tracking-tight" style={{ color: 'var(--text-primary)' }}>
          DarkNexus
        </div>
        <div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
          {title || 'Drug Intelligence & Evidence System'}
        </div>
      </div>

      <form onSubmit={submitSearch} className="relative flex-1 lg:flex-none lg:w-72 max-w-md">
        <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--text-muted)' }} />
        <input
          className="input pl-8 text-[13px]"
          placeholder="Search intelligence, entities, evidence…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </form>

      <div className="flex items-center gap-1 shrink-0">
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="btn btn-ghost p-2"
          title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
        >
          {theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        <button className="btn btn-ghost p-2 relative" title="Alerts">
          <Bell className="w-4 h-4" />
        </button>

        <div className="relative" ref={menuRef}>
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 pl-1.5 pr-2 py-1 rounded-lg transition"
            style={{ background: menuOpen ? 'var(--surface-hover)' : 'transparent' }}
          >
            <div className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold"
                 style={{ background: 'var(--accent-soft)', color: 'var(--accent)' }}>
              {initials}
            </div>
            <div className="hidden md:block text-left leading-tight">
              <div className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
                {user?.username || 'Not signed in'}
              </div>
              <div className="text-[10px] mono" style={{ color: 'var(--text-muted)' }}>
                {user?.badge_number || user?.role || ''}
              </div>
            </div>
            <ChevronDown className="w-3.5 h-3.5" style={{ color: 'var(--text-muted)' }} />
          </button>

          {menuOpen && (
            <div className="absolute right-0 mt-1 w-56 card p-1 z-50 animate-fade-up">
              <div className="px-3 py-2" style={{ borderBottom: '1px solid var(--border)' }}>
                <div className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
                  {user?.username}
                </div>
                <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  {user?.department || '—'}
                </div>
                {user?.role && (
                  <div className="text-[10px] mt-1 mono" style={{ color: 'var(--text-muted)' }}>
                    Role: {user.role}
                  </div>
                )}
              </div>
              <button
                onClick={() => { setMenuOpen(false); logout(); }}
                className="w-full flex items-center gap-2 px-3 py-2 text-[13px] rounded-md transition hover:bg-[var(--surface-hover)]"
                style={{ color: 'var(--text-secondary)' }}
              >
                <LogOut className="w-3.5 h-3.5" /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};

export const Footer = () => (
  <footer
    className="h-8 shrink-0 flex items-center justify-between px-4 text-[11px]"
    style={{
      background: 'var(--surface-card)',
      borderTop: '1px solid var(--border)',
      color: 'var(--text-muted)',
    }}
  >
    <div className="flex items-center gap-3">
      <span>Secure</span>
      <span>·</span>
      <span>Confidential</span>
      <span>·</span>
      <span>For Official Use Only</span>
    </div>
    <div>DarkNexus · Chandigarh Police</div>
  </footer>
);
