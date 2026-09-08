import React from 'react';

export const StatsCard = ({ title, value, subtitle, icon: Icon, color = "cyan", badge }) => {
  const colorMap = {
    cyan: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
    emerald: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    amber: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    rose: "text-rose-400 border-rose-500/30 bg-rose-500/10",
    purple: "text-purple-400 border-purple-500/30 bg-purple-500/10"
  };

  const gradientMap = {
    cyan: "from-cyan-500/5 to-transparent",
    emerald: "from-emerald-500/5 to-transparent",
    amber: "from-amber-500/5 to-transparent",
    rose: "from-rose-500/5 to-transparent",
    purple: "from-purple-500/5 to-transparent"
  };

  return (
    <div className="glass-card glass-card-hover rounded-xl p-5 relative overflow-hidden">
      {/* Subtle gradient background */}
      <div className={`absolute inset-0 bg-gradient-to-br ${gradientMap[color] || gradientMap.cyan} pointer-events-none`} />
      
      <div className="relative z-10">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs uppercase font-mono tracking-wider text-slate-400 mb-1">
              {title}
            </div>
            <div className="text-2xl font-bold font-mono text-slate-100 tracking-tight animate-count-pop">
              {value}
            </div>
            {subtitle && (
              <div className="text-[11px] text-slate-400 mt-1 font-mono">
                {subtitle}
              </div>
            )}
          </div>

          {Icon && (
            <div className={`p-2.5 rounded-lg border ${colorMap[color] || colorMap.cyan}`}>
              <Icon className="w-5 h-5" />
            </div>
          )}
        </div>

        {badge && (
          <div className="mt-3 inline-block text-[10px] font-mono px-2 py-0.5 rounded bg-[#14203b] border border-[#1c2d52] text-slate-300">
            {badge}
          </div>
        )}
      </div>
    </div>
  );
};

