// 项目切换器组件

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Modal, Portal, List, RadioButton, Button, Divider, Searchbar } from 'react-native-paper';
import { useProjects } from '@/hooks/useProjects';
import { Project } from '@/types';
import { Skeleton } from '@/components/ui/Skeleton';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';

interface ProjectSwitcherProps {
  visible: boolean;
  onDismiss: () => void;
  onSelect: (project: Project) => void;
  currentProjectId?: number;
}

export function ProjectSwitcher({
  visible,
  onDismiss,
  onSelect,
  currentProjectId,
}: ProjectSwitcherProps) {
  const { projects, isLoading, switchProject } = useProjects({ autoFetch: true });
  const { colors } = useTheme();
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = React.useState('');
  const [switching, setSwitching] = React.useState<number | null>(null);

  const filteredProjects = React.useMemo(() => {
    if (!searchQuery) return projects;
    return projects.filter(p =>
      p.name.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [projects, searchQuery]);

  const handleSelect = async (project: Project) => {
    if (project.id === currentProjectId) {
      onDismiss();
      return;
    }

    setSwitching(project.id);
    try {
      await switchProject(project.id);
      onSelect(project);
      onDismiss();
    } finally {
      setSwitching(null);
    }
  };

  return (
    <Portal>
      <Modal
        visible={visible}
        onDismiss={onDismiss}
        contentContainerStyle={styles.container}
      >
        <View style={styles.header}>
          <Searchbar
            placeholder={t('projectSwitcher.searchPlaceholder')}
            onChangeText={setSearchQuery}
            value={searchQuery}
            style={styles.searchbar}
          />
        </View>

        <Divider />

        {isLoading ? (
          <View style={styles.loading}>
            <Skeleton width="100%" height={60} />
            <Skeleton width="100%" height={60} style={{ marginTop: 8 }} />
            <Skeleton width="100%" height={60} style={{ marginTop: 8 }} />
          </View>
        ) : (
          <RadioButton.Group
            onValueChange={(value) => {
              const project = projects.find(p => p.id.toString() === value);
              if (project) handleSelect(project);
            }}
            value={currentProjectId?.toString()}
          >
            {filteredProjects.map((project) => (
              <List.Item
                key={project.id}
                title={project.name}
                description={project.description || t('projectSwitcher.noDesc')}
                left={() => (
                  <RadioButton
                    value={project.id.toString()}
                    disabled={switching === project.id}
                  />
                )}
                right={() =>
                  switching === project.id ? (
                    <Skeleton width={20} height={20} borderRadius={10} />
                  ) : project.isActive ? (
                    <List.Icon icon="check-circle" color={colors.primary} />
                  ) : null
                }
                onPress={() => handleSelect(project)}
                style={styles.listItem}
              />
            ))}
          </RadioButton.Group>
        )}

        <Divider />

        <View style={styles.footer}>
          <Button onPress={onDismiss} mode="outlined" style={styles.button}>
            {t('common.cancel')}
          </Button>
        </View>
      </Modal>
    </Portal>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#fff',
    margin: 24,
    borderRadius: 12,
    maxHeight: '80%',
  },
  header: {
    padding: 16,
  },
  searchbar: {
    elevation: 0,
    backgroundColor: '#f5f5f5',
  },
  loading: {
    padding: 16,
  },
  listItem: {
    paddingVertical: 8,
  },
  footer: {
    padding: 16,
  },
  button: {
    borderRadius: 8,
  },
});
