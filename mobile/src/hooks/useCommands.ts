// 指令下达 Hook - 封装向 Gateway 下达指令的逻辑
// 提供简洁的指令调用方式和状态管理

import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { commandApi } from '@/services/api';
import type {
  ExecuteCommandResponse,
} from '@/services/api/commands';

/** Hook 返回类型 */
interface UseCommandsReturn {
  isLoading: boolean;
  error: string | null;
  stop: (threadId: string, deviceKey?: string) => Promise<ExecuteCommandResponse>;
}

/**
 * 指令下达 Hook
 */
export function useCommands(): UseCommandsReturn {
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 停止执行
   */
  const stop = useCallback(async (
    threadId: string,
    deviceKey?: string
  ): Promise<ExecuteCommandResponse> => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await commandApi.stopExecution(threadId, deviceKey);
      
      if (response.code !== 0) {
        setError(response.message);
      }
      
      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : t('common.error.unknown');
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  return {
    isLoading,
    error,
    stop,
  };
}

export default useCommands;
