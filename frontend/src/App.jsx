import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { Sidebar } from './components/Sidebar';
import { Header, Footer } from './components/Header';

import { Login } from './pages/Login';
import { ChangePasswordGate } from './pages/ChangePasswordGate';
import { Overview } from './pages/Overview';
import { Intelligence } from './pages/Intelligence';
import { Sources } from './pages/Sources';
import { Blockchain } from './pages/Blockchain';
import { AuditLog } from './pages/AuditLog';

// Pages still on the previous visual language. They work against the real API;
// they have not yet been rebuilt on the new design system.
import { NetworkMap } from './pages/NetworkMap';
import { PunjabHeatmap } from './pages/PunjabHeatmap';
import { LiveSimulator } from './pages/LiveSimulator';
import { CTIProjects } from './pages/CTIProjects';
import { EntityExplorer } from './pages/EntityExplorer';
import { EvidenceVault } from './pages/EvidenceVault';
import { IntelVerification } from './pages/IntelVerification';
import { Reports } from './pages/Reports';
import { AIIntelligence } from './pages/AIIntelligence';

const Layout = ({ children, title }) => {
  const { isAuthenticated, isBootstrapping, mustChangePassword } = useAuth();

  // The stored token has not been checked with the server yet. Rendering the
  // login screen here would bounce a user with a perfectly valid session.
  if (isBootstrapping) {
    return (
      <div className="h-full flex items-center justify-center"
           style={{ background: 'var(--surface-page)' }}>
        <div className="text-center space-y-3">
          <div className="w-7 h-7 rounded-full mx-auto animate-spin"
               style={{ border: '2px solid var(--border)', borderTopColor: 'var(--accent)' }} />
          <p className="text-[12px]" style={{ color: 'var(--text-muted)' }}>Verifying session…</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  // An account still on its generated initial password cannot be used for
  // anything else until that password is replaced.
  if (mustChangePassword) return <ChangePasswordGate />;

  return (
    <div className="h-full flex" style={{ background: 'var(--surface-page)' }}>
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header title={title} />
        {/* Pages rebuilt on the design system manage their own scrolling.
            The legacy pages do not, and without overflow here their content
            scrolls the window instead - taking the header and navigation
            rail off-screen with it. */}
        <main className="flex-1 min-h-0 flex overflow-auto">{children}</main>
        <Footer />
      </div>
    </div>
  );
};

const page = (title, element) => <Layout title={title}>{element}</Layout>;

export default function App() {
  return (
    <AuthProvider>
      <Router>
        <Routes>
          <Route path="/login" element={<Login />} />

          <Route path="/overview" element={page('Operational Overview', <Overview />)} />
          <Route path="/intelligence" element={page('Intelligence Feed', <Intelligence />)} />
          <Route path="/targets" element={page('Surveillance Sources', <Sources />)} />
          <Route path="/simulator" element={page('Live Triage', <LiveSimulator />)} />

          <Route path="/entities" element={page('Entity Resolution', <EntityExplorer />)} />
          <Route path="/network" element={page('Network Analysis', <NetworkMap />)} />
          <Route path="/geospatial" element={page('Geospatial Analysis', <PunjabHeatmap />)} />
          <Route path="/blockchain" element={page('Blockchain Forensics', <Blockchain />)} />
          <Route path="/cti" element={page('Investigation Projects', <CTIProjects />)} />
          <Route path="/ai-search" element={page('Semantic Search & RAG', <AIIntelligence />)} />

          <Route path="/vault" element={page('Evidence Vault', <EvidenceVault />)} />
          <Route path="/verify" element={page('Intelligence Verification', <IntelVerification />)} />
          <Route path="/reports" element={page('Reports & Dossiers', <Reports />)} />
          <Route path="/audit" element={page('Audit Log', <AuditLog />)} />

          <Route path="/" element={<Navigate to="/overview" replace />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
  );
}
