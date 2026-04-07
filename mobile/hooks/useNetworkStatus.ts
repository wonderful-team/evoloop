// 网络状态监听 Hook

import { useState, useEffect, useCallback } from 'react';
import NetInfo, {
  NetInfoState,
  NetInfoWifiState,
  NetInfoCellularState,
} from '@react-native-community/netinfo';

interface NetworkState {
  isConnected: boolean;
  isInternetReachable: boolean | null;
  type: string;
  isWifi: boolean;
  isCellular: boolean;
  details: NetInfoWifiState | NetInfoCellularState | null;
}

export function useNetworkStatus() {
  const [networkState, setNetworkState] = useState<NetworkState>({
    isConnected: true,
    isInternetReachable: true,
    type: 'unknown',
    isWifi: false,
    isCellular: false,
    details: null,
  });

  useEffect(() => {
    // 初始检查
    NetInfo.fetch().then((state) => {
      updateNetworkState(state);
    });

    // 订阅网络变化
    const unsubscribe = NetInfo.addEventListener((state) => {
      updateNetworkState(state);
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const updateNetworkState = (state: NetInfoState) => {
    setNetworkState({
      isConnected: state.isConnected ?? false,
      isInternetReachable: state.isInternetReachable,
      type: state.type,
      isWifi: state.type === 'wifi',
      isCellular: state.type === 'cellular',
      details: state.details as NetInfoWifiState | NetInfoCellularState | null,
    });
  };

  // 刷新网络状态
  const refresh = useCallback(async () => {
    const state = await NetInfo.fetch();
    updateNetworkState(state);
    return state.isConnected ?? false;
  }, []);

  return {
    ...networkState,
    refresh,
  };
}

// 网络状态变化监听 Hook
export function useNetworkChange(
  onConnect: () => void,
  onDisconnect: () => void
) {
  useEffect(() => {
    const unsubscribe = NetInfo.addEventListener((state) => {
      if (state.isConnected) {
        onConnect();
      } else {
        onDisconnect();
      }
    });

    return () => {
      unsubscribe();
    };
  }, [onConnect, onDisconnect]);
}
