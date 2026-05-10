import React, { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';

type SaveHandler = () => Promise<void>;
type ResetHandler = () => void;

interface SettingsContextType {
  isDirty: boolean;
  isSaving: boolean;
  registerSaveHandler: (id: string, handler: SaveHandler) => void;
  unregisterSaveHandler: (id: string) => void;
  setComponentDirty: (id: string, dirty: boolean) => void;
  applyChanges: () => Promise<void>;
  resetDraft: () => void;
  registerResetHandler: (id: string, handler: ResetHandler) => void;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { t } = useTranslation();
  const [isSaving, setIsSaving] = useState(false);
  const [saveHandlers] = useState<Record<string, SaveHandler>>({});
  const [resetHandlers] = useState<Record<string, ResetHandler>>({});
  const [dirtyStates, setDirtyStates] = useState<Record<string, boolean>>({});

  const setComponentDirty = useCallback((id: string, dirty: boolean) => {
    setDirtyStates(prev => ({ ...prev, [id]: dirty }));
  }, []);

  const registerSaveHandler = useCallback((id: string, handler: SaveHandler) => {
    saveHandlers[id] = handler;
  }, [saveHandlers]);

  const unregisterSaveHandler = useCallback((id: string) => {
    delete saveHandlers[id];
    delete dirtyStates[id];
    delete resetHandlers[id];
  }, [saveHandlers, dirtyStates, resetHandlers]);

  const registerResetHandler = useCallback((id: string, handler: ResetHandler) => {
    resetHandlers[id] = handler;
  }, [resetHandlers]);

  const resetDraft = useCallback(() => {
    Object.values(resetHandlers).forEach(handler => handler());
    setDirtyStates({});
    toast.info(t('settings.draftReset'));
  }, [t, resetHandlers]);

  const isDirty = useMemo(() => Object.values(dirtyStates).some(d => d), [dirtyStates]);

  const applyChanges = async () => {
    setIsSaving(true);
    const toastId = toast.loading(t('settings.applyingChanges'));
    
    try {
      // Execute all save handlers
      await Promise.all(Object.values(saveHandlers).map(handler => handler()));
      
      toast.success(t('settings.applySuccess'), { id: toastId });
      // Clear dirty states after successful save
      setDirtyStates({});
    } catch (error) {
      console.error('Apply changes failed:', error);
      toast.error(t('settings.applyError'), { id: toastId });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <SettingsContext.Provider value={{
      isDirty,
      isSaving,
      registerSaveHandler,
      unregisterSaveHandler,
      setComponentDirty,
      applyChanges,
      resetDraft,
      registerResetHandler
    }}>
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = () => {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};
