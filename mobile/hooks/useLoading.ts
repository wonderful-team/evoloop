// 加载状态 Hook

import { useState, useCallback } from 'react';

interface LoadingState {
  isLoading: boolean;
  error: Error | null;
}

interface UseLoadingOptions {
  onError?: (error: Error) => void;
  onSuccess?: () => void;
}

export function useLoading(options: UseLoadingOptions = {}) {
  const [state, setState] = useState<LoadingState>({
    isLoading: false,
    error: null,
  });

  const execute = useCallback(
    async <T,>(
      promise: Promise<T>,
      customOptions?: UseLoadingOptions
    ): Promise<T | null> => {
      setState({ isLoading: true, error: null });

      try {
        const result = await promise;
        setState({ isLoading: false, error: null });
        customOptions?.onSuccess?.() || options.onSuccess?.();
        return result;
      } catch (error) {
        const err = error instanceof Error ? error : new Error(String(error));
        setState({ isLoading: false, error: err });
        customOptions?.onError?.(err) || options.onError?.(err);
        return null;
      }
    },
    [options]
  );

  const reset = useCallback(() => {
    setState({ isLoading: false, error: null });
  }, []);

  return {
    ...state,
    execute,
    reset,
  };
}

// 多个并行请求的加载状态
export function useMultipleLoading(count: number) {
  const [loadings, setLoadings] = useState<boolean[]>(new Array(count).fill(false));
  const [errors, setErrors] = useState<(Error | null)[]>(new Array(count).fill(null));

  const setLoading = useCallback((index: number, loading: boolean) => {
    setLoadings((prev) => {
      const next = [...prev];
      next[index] = loading;
      return next;
    });
  }, []);

  const setError = useCallback((index: number, error: Error | null) => {
    setErrors((prev) => {
      const next = [...prev];
      next[index] = error;
      return next;
    });
  }, []);

  const execute = useCallback(
    async <T,>(
      index: number,
      promise: Promise<T>
    ): Promise<T | null> => {
      setLoading(index, true);
      setError(index, null);

      try {
        const result = await promise;
        setLoading(index, false);
        return result;
      } catch (error) {
        const err = error instanceof Error ? error : new Error(String(error));
        setError(index, err);
        setLoading(index, false);
        return null;
      }
    },
    [setLoading, setError]
  );

  const isAnyLoading = loadings.some(Boolean);
  const hasAnyError = errors.some(Boolean);

  return {
    loadings,
    errors,
    isAnyLoading,
    hasAnyError,
    execute,
    setLoading,
    setError,
  };
}
