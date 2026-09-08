import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { apiClient, setSessionExpiredHandler } from '../api/client';

/*
 * Authentication state.
 *
 * The previous implementation initialised isAuthenticated to true and seeded a
 * hardcoded ADMIN user, so the route guard in App.jsx passed for anyone who
 * opened the page - the login screen was decorative. It also carried an
 * "offline mode" that accepted a password published in the README whenever the
 * backend was unreachable, and stored the literal string 'offline_demo_token'
 * as the credential.
 *
 * Authentication is now decided by the server. The only thing held here is a
 * token the server issued, and a session is considered valid only after the
 * server confirms it.
 */

const AuthContext = createContext(null);

const TOKEN_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';
const USER_KEY = 'user_info';

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  // Null until the stored token has been checked, so protected routes do not
  // bounce to /login during the first render of an already-valid session.
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [mustChangePassword, setMustChangePassword] = useState(false);

  const clearSession = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
    setUser(null);
    setIsAuthenticated(false);
    setMustChangePassword(false);
  }, []);

  // The API client calls this when a request fails authentication and the
  // refresh token cannot rescue it.
  useEffect(() => {
    setSessionExpiredHandler(() => clearSession());
  }, [clearSession]);

  // Confirm any stored token with the server before trusting it. A token in
  // localStorage proves nothing on its own: it may be expired, revoked, or
  // issued by a previous deployment with a different signing key.
  useEffect(() => {
    let cancelled = false;

    const verifyStoredSession = async () => {
      const token = localStorage.getItem(TOKEN_KEY);
      if (!token) {
        if (!cancelled) setIsBootstrapping(false);
        return;
      }

      try {
        const res = await apiClient.get('/api/auth/me');
        if (cancelled) return;
        const profile = res.data || {};
        const info = {
          username: profile.username,
          role: profile.role,
          badge_number: profile.badge_number,
          department: profile.department,
        };
        localStorage.setItem(USER_KEY, JSON.stringify(info));
        setUser(info);
        setIsAuthenticated(true);
        setMustChangePassword(Boolean(profile.must_change_password));
      } catch {
        if (!cancelled) clearSession();
      } finally {
        if (!cancelled) setIsBootstrapping(false);
      }
    };

    verifyStoredSession();
    return () => { cancelled = true; };
  }, [clearSession]);

  const login = async (username, password) => {
    const params = new URLSearchParams();
    params.append('username', username);
    params.append('password', password);

    const res = await apiClient.post('/api/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });

    const { access_token, refresh_token, role } = res.data;
    localStorage.setItem(TOKEN_KEY, access_token);
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);

    // Take the profile from the server rather than assuming a badge number.
    let info = { username, role };
    try {
      const me = await apiClient.get('/api/auth/me');
      info = {
        username: me.data.username ?? username,
        role: me.data.role ?? role,
        badge_number: me.data.badge_number,
        department: me.data.department,
      };
      setMustChangePassword(Boolean(me.data.must_change_password));
    } catch {
      // Sign-in succeeded; a profile fetch failure is not a reason to reject it.
    }

    localStorage.setItem(USER_KEY, JSON.stringify(info));
    setUser(info);
    setIsAuthenticated(true);
    return true;
  };

  const changePassword = async (currentPassword, newPassword) => {
    await apiClient.post('/api/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    setMustChangePassword(false);
  };

  const logout = useCallback(() => clearSession(), [clearSession]);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated,
        isBootstrapping,
        mustChangePassword,
        login,
        logout,
        changePassword,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);
