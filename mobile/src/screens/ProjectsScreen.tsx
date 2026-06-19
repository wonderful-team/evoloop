// 项目列表页面

import React, { useCallback, useState } from 'react';
import { View, StyleSheet, FlatList, RefreshControl, Alert } from 'react-native';
import { Text, Card, Chip, Portal, Dialog, Button } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { router } from '@/utils/navigation';
import { useProjects } from '@/hooks/useProjects';
import { useAuthStore } from '@/stores/authStore';
import { useDeviceStore } from '@/stores/deviceStore';
import { useTheme } from '@/theme';

import { Skeleton, ListSkeleton } from '@/components/ui/Skeleton';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { Header } from '@/components/common/Header';
import { Project, GLOBAL_PROJECT, isGlobalProject } from '@/types';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

// 游客模式下的登录提示组件
// 游客模式下的登录提示组件
function GuestLoginPrompt() {
  const { t } = useTranslation();

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.guestContainer}>
        <MaterialIcons name="folder" size={64} color="#9CA3AF" />
        <Text variant="headlineMedium" style={styles.guestTitle}>
          {t('projects.managementTitle')}
        </Text>
        <Text variant="bodyMedium" style={styles.guestText}>
          {t('projects.guestDesc')}
        </Text>
        <Button
          mode="contained"
          style={styles.loginButton}
          onPress={() => router.push('Auth')}
        >
          {t('auth.login.submit')}
        </Button>
        <Button
          mode="text"
          style={styles.backButton}
          onPress={() => router.back()}
        >
          {t('projects.backToHome')}
        </Button>
      </View>
    </SafeAreaView>
  );
}

const ProjectsContent = () => {
  const { t } = useTranslation();
  const { isLoggedIn } = useAuthStore();
  const { colors } = useTheme();

  const {
    projects,
    currentProject,
    isGlobalMode,
    isLoading,
    error,
    refresh,
    switchProject,
    setGlobalMode,
  } = useProjects({ autoFetch: isLoggedIn }); // 只有登录后才自动获取

  const currentDevice = useDeviceStore(state => state.currentDevice);

  const [refreshing, setRefreshing] = useState(false);

  // 游客模式显示登录提示
  if (!isLoggedIn) {
    return <GuestLoginPrompt />;
  }

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  }, [refresh]);

  const handleProjectPress = useCallback(async (project: Project) => {
    if (isGlobalProject(project)) {
      setGlobalMode(true);
      router.back();
    } else if (!currentDevice) {
      // 没有选中设备时不能切换项目，弹窗提示
      Alert.alert(t('common.tip'), t('projects.selectDeviceFirst'));
      return;
    } else {
      try {
        await switchProject(project.id);
        router.back();
      } catch (e) {
        console.error('切换项目失败:', e);
      }
    }
  }, [switchProject, setGlobalMode, currentDevice, t]);

  const renderItem = useCallback(({ item }: { item: Project }) => (
    <Card
      style={[
        styles.card,
        currentProject?.id === item.id && [styles.activeCard, { borderColor: colors.primary }],
      ]}
      onPress={() => handleProjectPress(item)}
    >
      <Card.Content>
        <View style={styles.itemHeader}>
          <View style={[styles.iconContainer, { backgroundColor: colors.surfaceVariant }]}>
            <MaterialIcons name="folder" size={28} color={colors.primary} />
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
              style={[styles.activeChip, { backgroundColor: colors.primaryContainer }]}
              textStyle={{ color: colors.primary }}
            >
              {t('projects.current')}
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
  ), [currentProject, handleProjectPress, colors]);

  if (isLoading && projects.length === 0) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.pageHeader}>
          <Skeleton width={150} height={28} />
        </View>
        <ListSkeleton count={4} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <Header title={t('projects.title')} showBack />

      <View style={styles.pageHeader}>
        <Text variant="bodySmall" style={{ opacity: 0.6 }}>
          {isGlobalMode ? t('projects.currentGlobalMode') : currentProject ? `${t('projects.currentProjectPrefix')}${currentProject.name}` : t('projects.pleaseSelectProject')}
        </Text>
      </View>

      {error ? (
        <View style={styles.centerContent}>
          <Text style={styles.errorText}>
            {t('projects.loadFailed')}{error.message}
          </Text>
          <Button onPress={refresh} mode="contained" style={styles.retryButton}>
            {t('common.retry')}
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
          ListHeaderComponent={
            <Card
              style={[
                styles.card,
                styles.globalCard,
                isGlobalMode && [styles.activeCard, { borderColor: colors.primary }],
              ]}
              onPress={() => handleProjectPress(GLOBAL_PROJECT)}
            >
              <Card.Content>
                <View style={styles.itemHeader}>
                  <View style={[styles.iconContainer, { backgroundColor: '#E3F2FD' }]}>
                    <MaterialIcons name="public" size={28} color="#1976D2" />
                  </View>
                  <View style={styles.info}>
                    <Text variant="titleMedium" style={styles.name}>
                      {t('projects.globalMode')}
                    </Text>
                    <Text variant="bodySmall" style={styles.path}>
                      {t('projects.globalModeDesc')}
                    </Text>
                  </View>
                  {isGlobalMode && (
                    <Chip
                      icon="check-circle"
                      compact
                      style={[styles.activeChip, { backgroundColor: colors.primaryContainer }]}
                      textStyle={{ color: colors.primary }}
                    >
                      {t('projects.current')}
                    </Chip>
                  )}
                </View>
              </Card.Content>
            </Card>
          }
        />
      )}


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
  pageHeader: {
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 12,
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
  },
  globalCard: {
    marginBottom: 12,
    backgroundColor: '#FAFBFC',
  },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
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
    backgroundColor: 'transparent',
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
    color: '#757575',
  },
  // 游客模式样式
  guestContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  guestTitle: {
    fontWeight: 'bold',
    marginTop: 24,
    marginBottom: 12,
  },
  guestText: {
    textAlign: 'center',
    color: '#6B7280',
    marginBottom: 32,
    lineHeight: 22,
  },
  loginButton: {
    minWidth: 200,
    marginBottom: 12,
  },
  backButton: {
    minWidth: 200,
  },
});
