/**
 * EvoLoop 更新检查 Provider
 * 
 * 在应用初始化时启动更新服务
 * 需要在应用根组件中包裹使用
 * 
 * 使用示例:
 * ```tsx
 * function App() {
 *   return (
 *     <UpdateProvider>
 *       <YourApp />
 *     </UpdateProvider>
 *   );
 * }
 * ```
 */

import React, { useEffect, useState, useCallback, createContext, useContext } from 'react';
import { updateService } from '@/services/updateService';
import type { UpdateCheckResult } from '@/hooks/useVersion';
import { UpdateNotification } from './UpdateNotification';

/** 更新上下文类型 */
interface UpdateContextType {
  /** 当前更新信息 */
  updateInfo: UpdateCheckResult | null;
  /** 是否正在检查 */
  isChecking: boolean;
  /** 手动检查更新 */
  checkForUpdates: (force?: boolean) => Promise<UpdateCheckResult>;
  /** 跳过当前版本 */
  skipVersion: (version: string) => void;
  /** 关闭更新提示 */
  dismissUpdate: () => void;
}

const UpdateContext = createContext<UpdateContextType | undefined>(undefined);

/** 使用更新上下文的 Hook */
export function useUpdate(): UpdateContextType {
  const context = useContext(UpdateContext);
  if (!context) {
    throw new Error('useUpdate must be used within UpdateProvider');
  }
  return context;
}

interface UpdateProviderProps {
  children: React.ReactNode;
  /** 是否自动启动更新服务 */
  autoInit?: boolean;
  /** 自定义配置 */
  config?: {
    baseUrl?: string;
    checkInterval?: number;
    startupDelay?: number;
  };
}

export const UpdateProvider: React.FC<UpdateProviderProps> = ({
  children,
  autoInit = true,
  config = {},
}) => {
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResult | null>(null);
  const [isChecking, setIsChecking] = useState(false);
  const [showNotification, setShowNotification] = useState(false);

  // 初始化更新服务
  useEffect(() => {
    if (autoInit) {
      // 应用自定义配置
      const service = updateService;
      service.init();

      return () => {
        service.destroy();
      };
    }
  }, [autoInit, config]);

  /**
   * 手动检查更新
   */
  const checkForUpdates = useCallback(async (force = false): Promise<UpdateCheckResult> => {
    setIsChecking(true);
    
    try {
      const result = await updateService.performCheck('manual', force);
      
      if (result.hasUpdate) {
        setUpdateInfo(result);
        setShowNotification(true);
      }
      
      return result;
    } finally {
      setIsChecking(false);
    }
  }, []);

  /**
   * 跳过指定版本
   */
  const skipVersion = useCallback((version: string) => {
    updateService.skipVersion(version);
    setShowNotification(false);
  }, []);

  /**
   * 关闭更新提示
   */
  const dismissUpdate = useCallback(() => {
    setShowNotification(false);
  }, []);

  /**
   * 执行更新
   */
  const handleUpdate = useCallback(() => {
    if (updateInfo?.downloadUrl) {
      window.open(updateInfo.downloadUrl, '_blank');
    }
    setShowNotification(false);
  }, [updateInfo]);

  const contextValue: UpdateContextType = {
    updateInfo,
    isChecking,
    checkForUpdates,
    skipVersion,
    dismissUpdate,
  };

  return (
    <UpdateContext.Provider value={contextValue}>
      {children}
      
      {showNotification && updateInfo && (
        <UpdateNotification
          updateInfo={updateInfo}
          onClose={dismissUpdate}
          onUpdate={handleUpdate}
        />
      )}
    </UpdateContext.Provider>
  );
};

export default UpdateProvider;
