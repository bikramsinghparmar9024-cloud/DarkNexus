import { useState, useEffect, useCallback, useRef } from 'react';
import { apiClient, describeApiError } from '../api/client';

/**
 * Fetch a resource, tracking loading, data and error as three separate things.
 *
 * Pages previously collapsed all failures into "render demo data", so an
 * outage, an expired session and an empty database looked identical. Keeping
 * the error distinct is what lets the UI say which one happened.
 */
export function useApi(path, { params, skip = false, transform } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(!skip);

  // Serialised so an inline object literal does not retrigger every render.
  const paramKey = JSON.stringify(params ?? null);
  const transformRef = useRef(transform);
  transformRef.current = transform;

  const [reloadToken, setReloadToken] = useState(0);
  const reload = useCallback(() => setReloadToken((n) => n + 1), []);

  useEffect(() => {
    if (skip || !path) {
      setLoading(false);
      return undefined;
    }

    let cancelled = false;
    const controller = new AbortController();

    setLoading(true);
    setError(null);

    apiClient
      .get(path, { params: params ?? undefined, signal: controller.signal })
      .then((res) => {
        if (cancelled) return;
        const value = transformRef.current ? transformRef.current(res.data) : res.data;
        setData(value);
      })
      .catch((err) => {
        if (cancelled || err.name === 'CanceledError' || err.code === 'ERR_CANCELED') return;
        setError(describeApiError(err));
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, paramKey, skip, reloadToken]);

  return { data, error, loading, reload };
}

/**
 * Run a mutation, exposing its in-flight and error state.
 *
 * Buttons that trigger real work need to show that it is happening; the old
 * pages faked this with a two-second timer.
 */
export function useMutation(method = 'post') {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async (path, body, config) => {
    setBusy(true);
    setError(null);
    try {
      const res = await apiClient[method](path, body, config);
      return res.data;
    } catch (err) {
      const described = describeApiError(err);
      setError(described);
      throw Object.assign(err, { described });
    } finally {
      setBusy(false);
    }
  }, [method]);

  return { run, busy, error, clearError: () => setError(null) };
}
