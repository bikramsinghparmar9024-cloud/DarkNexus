import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard, Radar, Users, FileArchive, Share2, MapPin, FileText,
  ScrollText, Radio, Coins, CheckCircle2, Target, Sparkles,
} from 'lucide-react';

/*
 * Navigation rail.
 *
 * Grouped by what an investigator is doing rather than by which subsystem
 * produced the data: collection, then analysis, then evidence handling.
 * Every entry here maps to a working backend capability - nothing is listed
 * that cannot actually be opened.
 */

const SECTIONS = [
  {
    items: [
      { to: '/overview', label: 'Overview', icon: LayoutDashboard },
    ],
  },
  {
    title: 'Collection',
    items: [
      { to: '/intelligence', label: 'Intelligence', icon: Radar },
      { to: '/targets', label: 'Sources', icon: Target },
      { to: '/simulator', label: 'Live Triage', icon: Radio },
    ],
  },
  {
    title: 'Analysis',
    items: [
      { to: '/entities', label: 'Entities', icon: Users },
      { to: '/network', label: 'Networks', icon: Share2 },
      { to: '/geospatial', label: 'Geospatial', icon: MapPin },
      { to: '/blockchain', label: 'Blockchain', icon: Coins },
      { to: '/ai-search', label: 'Semantic Search', icon: Sparkles },
      { to: '/cti', label: 'Projects', icon: FileText },
    ],
  },
  {
    title: 'Evidence',
    items: [
      { to: '/vault', label: 'Evidence Vault', icon: FileArchive },
      { to: '/verify', label: 'Verification', icon: CheckCircle2 },
      { to: '/reports', label: 'Reports', icon: ScrollText },
      { to: '/audit', label: 'Audit Log', icon: ScrollText },
    ],
  },
];

const railItemStyle = ({ isActive }) => ({
  background: isActive ? 'var(--rail-bg-active)' : 'transparent',
  color: isActive ? 'var(--rail-text-active)' : 'var(--rail-text)',
});

export const Sidebar = () => (
  <nav
    className="w-[210px] shrink-0 flex flex-col"
    style={{ background: 'var(--rail-bg)', borderRight: '1px solid var(--rail-border)' }}
  >
    <div className="flex-1 scroll-area py-3">
      {SECTIONS.map((section, i) => (
        <div key={i} className="mb-4">
          {section.title && (
            <div className="px-4 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em]"
                 style={{ color: 'var(--rail-muted)' }}>
              {section.title}
            </div>
          )}
          <div className="px-2 space-y-0.5">
            {section.items.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                style={railItemStyle}
                className="flex items-center gap-2.5 px-3 py-[7px] rounded-md text-[13px] font-medium transition-colors hover:brightness-125"
              >
                <Icon className="w-4 h-4 shrink-0" />
                <span className="truncate">{label}</span>
              </NavLink>
            ))}
          </div>
        </div>
      ))}
    </div>

    <div className="px-4 py-3 text-[10px] leading-relaxed"
         style={{ borderTop: '1px solid var(--rail-border)', color: 'var(--rail-muted)' }}>
      <div className="font-semibold" style={{ color: 'var(--rail-text)' }}>DarkNexus v1.0.0</div>
      <div>Chandigarh Police</div>
      <div>For Official Use Only</div>
    </div>
  </nav>
);
