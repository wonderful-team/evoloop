// 项目列表页面

import React, { useCallback, useState } from 'react';
import { View, StyleSheet, FlatList, RefreshControl } from 'react-native';
import { Text, Card, Chip, FAB, Portal, Dialog, Button } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useProjects } from '@/hooks/useProjects';
import { ProjectSwitcher } from '@/components/device/ProjectSwitcher';
import { Skeleton, ListSkeleton } from '@/components/ui/Skeleton';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { Project } from '@/types';
import { MaterialIcons } from '@expo/vector-icons';

function ProjectsContent() {
  const { t } = useTranslation();
  const {
    projects,
    currentProject,
    isLoading,
    error,
    refresh,
    switchProject,
  } = useProjects({ autoFetch: true });

  const [refreshing, setRefreshing] = useState(false);
  const [switcherVisible, setSwitcherVisible] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [dialogVisible, setDialogVisible] = useState(false);
  const [switching, setSwitching] = useState(false);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  }, [refresh]);

  const handleProjectPress = useCallback((project: Project) => {
    setSelectedProject(project);
    setDialogVisible(true);
  }, []);

  const handleSwitch = useCallback(async () => {
    if (!selectedProject) return;
    
    setSwitching(true);
    try {
      await switchProject(selectedProject.id);
      setDialogVisible(false);
    } finally {
      setSwitching(false);
    }
  }, [selectedProject, switchProject]);

  const renderItem = useCallback(({ item }: { item: Project }) => (
    <Card
      style={[
        styles.card,
        currentProject?.id === item.id && styles.activeCard,
      ]}
      onPress={() => handleProjectPress(item)}
    >
      <Card.Content>
        <View style={styles.header}>
          <View style={styles.iconContainer}>
            <MaterialIcons name="folder" size={28} color="#0066FF" />
          </View>
          <View style={styles.info}>
            <Text variant="titleMedium" style={styles.name}>
              {item.name}
            </Text>
            <Text variant="bodySmall" style={styles.path}>
              {item.rootPath}
            </Text>
          </View>
          {currentProject?.id === item.id && (
            <Chip
              icon="check-circle"
              compact
              style={styles.activeChip}
              textStyle={{ color: '#00C853' }}
            >
              当前
            </Chip>
          )}
        </View>
        
        {item.description && (
          <Text variant="bodySmall" style={styles.description}>
            {item.description}
          </Text>
        )}
      </Card.Content>
    </Card>
  ), [currentProject, handleProjectPress]);

  if (isLoading && projects.length === 0) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <Skeleton width={150} height={28} />
        </View>
        <ListSkeleton count={4} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.header}>
        <Text variant="headlineMedium" style={styles.title}>
          {t('projects.title')}
        </Text>
        {currentProject && (
          <Card style={styles.currentCard}>
            <Card.Content style={styles.currentCardContent}>
              <MaterialIcons name="folder-open" size={24} color="#0066FF" />
              <View style={styles.currentInfo}>
                <Text variant="bodySmall" style={styles.currentLabel}>
                  当前项目
                </Text>
                <Text variant="titleSmall" numberOfLines={1}>
                  {currentProject.name}
                </Text>
              </View>
              <Button
                mode="text"
                onPress={() => setSwitcherVisible(true)}
                compact
              >
                切换
              </Button>
            </Card.Content>
          </Card>
        )}
      </View>

      {error ? (
        <View style={styles.centerContent}>
          <Text style={styles.errorText}>
            加载失败: {error.message}
          </Text>
          <Button onPress={refresh} mode="contained" style={styles.retryButton}>
            重试
          </Button>
        </View>
      ) : projects.length === 0 ? (
        <View style={styles.centerContent}>
          <Text style={styles.emptyText}>
            {t('projects.noProjects')}
          </Text>
        </View>
      ) : (
        <FlatList
          data={projects}
          renderItem={renderItem}
          keyExtractor={(item) => item.id.toString()}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        />
      )}

      <ProjectSwitcher
        visible={switcherVisible}
        onDismiss={() => setSwitcherVisible(false)}
        onSelect={() => {}}
        currentProjectId={currentProject?.id}
      />

      <Portal>
        <Dialog visible={dialogVisible} onDismiss={() => setDialogVisible(false)}>
          <Dialog.Title>{selectedProject?.name}</Dialog.Title>
          <Dialog.Content>
            <Text variant="bodyMedium">
              切换到此项目？这将同步到所有已连接的设备。
            </Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setDialogVisible(false)}>取消</Button>
            <Button
              onPress={handleSwitch}
              loading={switching}
              disabled={switching}
              mode="contained"
            >
              切换
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>

      <FAB
        icon="swap-horizontal"
        style={styles.fab}
        onPress={() => setSwitcherVisible(true)}
        label="切换项目"
      />
    </SafeAreaView>
  );
}

export default function ProjectsScreen() {
  return (
    <ErrorBoundary>
      <ProjectsContent />
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 12,
  },
  currentCard: {
    marginBottom: 8,
    backgroundColor: '#f0f7ff',
  },
  currentCardContent: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  currentInfo: {
    flex: 1,
    marginLeft: 12,
  },
  currentLabel: {
    opacity: 0.6,
  },
  list: {
    padding: 8,
  },
  card: {
    marginHorizontal: 8,
    marginVertical: 6,
  },
  activeCard: {
    borderWidth: 2,
    borderColor: '#0066FF',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#f0f7ff',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  info: {
    flex: 1,
  },
  name: {
    fontWeight: '600',
  },
  path: {
    opacity: 0.6,
    marginTop: 2,
  },
  activeChip: {
    backgroundColor: '#E8F5E9',
  },
  description: {
    marginTop: 8,
    opacity: 0.7,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  errorText: {
    color: '#FF3D00',
    marginBottom: 16,
  },
  retryButton: {
    minWidth: 120,
  },
  emptyText: {
    fontSize: 18,
    fontWeight: '600',
    color: '#666',
  },
  fab: {
    position: 'absolute',
    margin: 16,
    right: 0,
    bottom: 0,
    backgroundColor: '#0066FF',
  },
});
