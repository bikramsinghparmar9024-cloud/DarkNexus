import React, { useState } from 'react';
import { Coins, Search, ExternalLink, Loader2, ShieldCheck, ShieldAlert } from 'lucide-react';
import { useApi, useMutation } from '../hooks/useApi';
import {
  PageHeader, SectionCard, AsyncBoundary, EmptyState, Field, Mono, ErrorState,
} from '../components/ui';

/*
 * Blockchain forensics.
 *
 * The previous page held two constants - DEMO_ADDRESSES and DEMO_TRANSACTIONS -
 * and made no request of any kind, despite /api/blockchain/lookup being fully
 * functional against the Blockstream API. Every figure below is live chain data.
 */

export const Blockchain = () => {
  const [address, setAddress] = useState('');
  const [crypto, setCrypto] = useState('BTC');
  const [result, setResult] = useState(null);
  const lookup = useMutation('post');

  // Wallets harvested from collected intelligence, so an investigator can pick
  // one rather than retyping a 34-character address by hand.
  const tracked = useApi('/api/ai/entities-summary');

  const submit = async (e) => {
    e.preventDefault();
    if (!address.trim()) return;
    setResult(null);
    try {
      const data = await lookup.run('/api/blockchain/lookup', {
        address: address.trim(),
        crypto_type: crypto,
      });
      setResult(data);
    } catch {
      // Surfaced through lookup.error below.
    }
  };

  const overview = result?.overview;
  const txs = result?.recent_transactions || [];

  return (
    <div className="flex-1 min-w-0 scroll-area">
      <div className="p-5 space-y-4 max-w-[1200px]">
        <PageHeader
          breadcrumb="Analysis / Blockchain"
          title="Blockchain Forensics"
          description="Trace cryptocurrency addresses recovered from collected intelligence against live chain data."
        />

        <SectionCard>
          <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
            <div className="flex-1 min-w-[260px]">
              <label className="label block mb-1">Address</label>
              <input
                className="input mono"
                placeholder="Paste a Bitcoin or Ethereum address"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
              />
            </div>
            <div>
              <label className="label block mb-1">Chain</label>
              <select className="input w-auto" value={crypto} onChange={(e) => setCrypto(e.target.value)}>
                <option value="BTC">Bitcoin</option>
                <option value="ETH">Ethereum</option>
              </select>
            </div>
            <button type="submit" className="btn btn-primary" disabled={lookup.busy || !address.trim()}>
              {lookup.busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
              Trace
            </button>
          </form>

          {lookup.error && <div className="mt-3"><ErrorState error={lookup.error} compact /></div>}
        </SectionCard>

        {result && (
          <SectionCard title="Chain data">
            {overview?.valid === false ? (
              <div className="flex items-start gap-2 text-[13px]" style={{ color: 'var(--risk-high-text)' }}>
                <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
                <div>
                  <p className="font-medium">This address could not be queried.</p>
                  <p className="text-[12px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                    {overview.error || 'The chain returned no record for it.'} A mistyped
                    or OCR-misread address looks exactly like an unused one, so treat a
                    blank result as unconfirmed rather than as a dead end.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-[13px]" style={{ color: 'var(--status-active)' }}>
                  <ShieldCheck className="w-4 h-4" /> Address resolved on {overview?.network || 'chain'}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
                  <Field label="Address"><Mono>{overview?.address}</Mono></Field>
                  <Field
                    label="Balance"
                    value={overview?.current_balance_btc !== undefined
                      ? `${overview.current_balance_btc} BTC`
                      : overview?.balance_eth}
                  />
                  <Field
                    label="Total received"
                    value={overview?.total_received_btc !== undefined
                      ? `${overview.total_received_btc} BTC`
                      : '—'}
                  />
                  <Field label="Transactions" value={overview?.total_tx_count} />
                </div>

                <div>
                  <div className="label mb-2">Recent transactions</div>
                  {txs.length === 0 ? (
                    <p className="text-[13px]" style={{ color: 'var(--text-muted)' }}>
                      No confirmed transactions returned for this address.
                    </p>
                  ) : (
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Transaction</th><th>Confirmed</th><th>Inputs</th>
                          <th>Outputs</th><th>Fee</th>
                        </tr>
                      </thead>
                      <tbody>
                        {txs.map((tx) => (
                          <tr key={tx.txid}>
                            <td>
                              <a
                                className="link mono text-[12px] inline-flex items-center gap-1"
                                href={`https://blockstream.info/tx/${tx.txid}`}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {tx.txid?.slice(0, 20)}… <ExternalLink className="w-3 h-3" />
                              </a>
                            </td>
                            <td className="text-[12px]">{tx.confirmed ? 'Yes' : 'Pending'}</td>
                            <td className="text-[12px]">{tx.vin_count}</td>
                            <td className="text-[12px]">{tx.vout_count}</td>
                            <td className="text-[12px] mono">{tx.fee_sats} sat</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}
          </SectionCard>
        )}

        <SectionCard title="Wallets seen in collected intelligence">
          <AsyncBoundary
            loading={tracked.loading}
            error={tracked.error}
            onRetry={tracked.reload}
            isEmpty={!tracked.data?.crypto_wallets?.length}
            empty={
              <EmptyState
                icon={Coins}
                title="No wallet addresses recovered yet"
                description="Addresses extracted from collected records appear here once they pass checksum validation. A misread address is never listed as traceable."
              />
            }
          >
            <div className="flex flex-wrap gap-2">
              {(tracked.data?.crypto_wallets || []).map((w) => (
                <button
                  key={w}
                  onClick={() => { setAddress(w); setResult(null); }}
                  className="pill mono transition"
                  style={{
                    background: 'var(--surface-sunken)',
                    color: 'var(--text-secondary)',
                    borderColor: 'var(--border)',
                  }}
                >
                  {w.slice(0, 22)}…
                </button>
              ))}
            </div>
          </AsyncBoundary>
        </SectionCard>
      </div>
    </div>
  );
};
