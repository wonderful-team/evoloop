// 引用选择器 - 支持 @ 引用文件、历史消息等

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  StyleSheet,
  Modal,
  TouchableOpacity,
  ScrollView,
  TextInput,
  ActivityIndicator,
} from 'react-native';
import { Text, IconButton, Divider, Chip } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { MessageReference, SearchReferenceResult, MemoryConcept } from '@/types/conversation';
import * as conversationApi from '@/services/api/conversations';
import * as projectApi from '@/services/api/projects';

interface ReferencePickerProps {
  visible: boolean;
  onDismiss: () => void;
  onSelect: (reference: MessageReference) => void;
  projectId?: number;
  conversationId?: string;
}

type TabType = 'history' | 'files' | 'memory';

export function ReferencePicker({
  visible,
  onDismiss,
  onSelect,
  projectId,
  conversationId,
}: ReferencePickerProps) {
  const { colors } = useTheme();
  const [activeTab, setActiveTab] = useState<TabType>('history');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SearchReferenceResult[]>([]);
  const [memories, setMemories] = useState<MemoryConcept[]>([]);
  const [recentMessages, setRecentMessages] = useState<SearchReferenceResult[]>([]);

  // 加载数据
  useEffect(() => {
    if (!visible) return;

    const loadData = async () => {
      setIsLoading(true);
      try {
        if (activeTab === 'history' && conversationId) {
          // 加载最近的消息
          const history = await conversationApi.getConversationHistory(conversationId, undefined, 10);
          const formatted = history.messages.map(msg => ({
            id: msg.id,
            type: 'message' as const,
            name: msg.content.slice(0, 50) + (msg.content.length > 50 ? '...' : ''),
            content: msg.content,
            score: 1,
            timestamp: new Date(msg.timestamp).toISOString(),
          }));
          setRecentMessages(formatted);
          setResults(formatted);
        } else if (activeTab === 'memory' && projectId) {
          // 加载项目记忆
          const memoryList = await conversationApi.getMemories(projectId);
          setMemories(memoryList);
        } else if (activeTab === 'files' && projectId) {
          // 加载项目文件
          const files = await projectApi.getProjectFiles(projectId);
          const fileResults: SearchReferenceResult[] = files.map(f => ({
            id: f.path,
            type: 'file',
            name: f.name,
            content: f.path,
            score: 1,
          }));
          setResults(fileResults);
        }
      } catch (error) {
        console.error('Failed to load reference data:', error);
      } finally {
        setIsLoading(false);
      }
    };

    loadData();
  }, [visible, activeTab, projectId, conversationId]);

  // 搜索
  const handleSearch = useCallback(async (query: string) => {
    setSearchQuery(query);
    if (!query.trim()) {
      setResults(recentMessages);
      return;
    }

    setIsLoading(true);
    try {
      if (activeTab === 'history' && conversationId) {
        // 搜索历史消息
        const history = await conversationApi.getConversationHistory(conversationId);
        const filtered = history.messages
          .filter(msg => msg.content.toLowerCase().includes(query.toLowerCase()))
          .map(msg => ({
            id: msg.id,
            type: 'message' as const,
            name: msg.content.slice(0, 50) + (msg.content.length > 50 ? '...' : ''),
            content: msg.content,
            score: 1,
            timestamp: new Date(msg.timestamp).toISOString(),
          }));
        setResults(filtered);
      }
    } catch (error) {
      console.error('Search failed:', error);
    } finally {
      setIsLoading(false);
    }
  }, [activeTab, conversationId, recentMessages]);

  const handleSelect = (item: SearchReferenceResult | MemoryConcept) => {
    let reference: MessageReference;

    if ('type' in item) {
      reference = {
        type: item.type as 'message' | 'file',
        id: item.id,
        name: item.name,
        detail: item.content,
      };
    } else {
      reference = {
        type: 'memory',
        id: item.id,
        name: item.name,
        detail: item.description.slice(0, 100),
      };
    }

    onSelect(reference);
    onDismiss();
  };

  const renderTabContent = () => {
    if (isLoading) {
      return (
        <View style={styles.centerContent}>
          <ActivityIndicator color={colors.primary} />
        </View>
      );
    }

    if (activeTab === 'memory') {
      if (memories.length === 0) {
        return (
          <View style={styles.centerContent}>
            <MaterialIcons name="memory" size={48} color={colors.onSurfaceVariant} />
            <Text style={{ color: colors.onSurfaceVariant, marginTop: 8 }}>暂无记忆</Text>
          </View>
        );
      }

      return (
        <ScrollView style={styles.list}>
          {memories.map(memory => (
            <TouchableOpacity
              key={memory.id}
              style={[styles.item, { borderBottomColor: colors.outline + '20' }]}
              onPress={() => handleSelect(memory)}
            >
              <View style={styles.itemIcon}>
                <MaterialIcons name="memory" size={20} color={colors.primary} />
              </View>
              <View style={styles.itemContent}>
                <Text variant="bodyMedium" style={{ color: colors.onSurface }} numberOfLines={1}>
                  {memory.name}
                </Text>
                <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }} numberOfLines={2}>
                  {memory.description}
                </Text>
              </View>
              <MaterialIcons name="chevron-right" size={20} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          ))}
        </ScrollView>
      );
    }

    if (results.length === 0) {
      return (
        <View style={styles.centerContent}>
          <MaterialIcons name="search-off" size={48} color={colors.onSurfaceVariant} />
          <Text style={{ color: colors.onSurfaceVariant, marginTop: 8 }}>未找到相关内容</Text>
        </View>
      );
    }

    return (
      <ScrollView style={styles.list}>
        {results.map(item => (
          <TouchableOpacity
            key={item.id}
            style={[styles.item, { borderBottomColor: colors.outline + '20' }]}
            onPress={() => handleSelect(item)}
          >
            <View style={styles.itemIcon}>
              <MaterialIcons
                name={item.type === 'message' ? 'chat' : 'insert-drive-file'}
                size={20}
                color={colors.primary}
              />
            </View>
            <View style={styles.itemContent}>
              <Text variant="bodyMedium" style={{ color: colors.onSurface }} numberOfLines={1}>
                {item.name}
              </Text>
              {item.timestamp && (
                <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
                  {new Date(item.timestamp).toLocaleString()}
                </Text>
              )}
            </View>
            <MaterialIcons name="chevron-right" size={20} color={colors.onSurfaceVariant} />
          </TouchableOpacity>
        ))}
      </ScrollView>
    );
  };

  return (
    <Modal
      visible={visible}
      onRequestClose={onDismiss}
      animationType="slide"
      presentationStyle="pageSheet"
    >
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        {/* 头部 */}
        <View style={styles.header}>
          <Text variant="titleLarge" style={{ color: colors.onSurface }}>
            引用内容
          </Text>
          <IconButton icon="close" size={24} onPress={onDismiss} />
        </View>

        {/* 搜索框 */}
        <View style={[styles.searchBar, { backgroundColor: colors.surfaceVariant }]}>
          <MaterialIcons name="search" size={20} color={colors.onSurfaceVariant} />
          <TextInput
            style={[styles.searchInput, { color: colors.onSurface }]}
            placeholder="搜索..."
            placeholderTextColor={colors.onSurfaceVariant}
            value={searchQuery}
            onChangeText={handleSearch}
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => handleSearch('')}>
              <MaterialIcons name="close" size={20} color={colors.onSurfaceVariant} />
            </TouchableOpacity>
          )}
        </View>

        {/* Tab 切换 */}
        <View style={styles.tabs}>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'history' && styles.activeTab]}
            onPress={() => setActiveTab('history')}
          >
            <MaterialIcons
              name="history"
              size={20}
              color={activeTab === 'history' ? colors.primary : colors.onSurfaceVariant}
            />
            <Text
              variant="labelMedium"
              style={{ color: activeTab === 'history' ? colors.primary : colors.onSurfaceVariant }}
            >
              历史消息
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'files' && styles.activeTab]}
            onPress={() => setActiveTab('files')}
          >
            <MaterialIcons
              name="folder"
              size={20}
              color={activeTab === 'files' ? colors.primary : colors.onSurfaceVariant}
            />
            <Text
              variant="labelMedium"
              style={{ color: activeTab === 'files' ? colors.primary : colors.onSurfaceVariant }}
            >
              项目文件
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.tab, activeTab === 'memory' && styles.activeTab]}
            onPress={() => setActiveTab('memory')}
          >
            <MaterialIcons
              name="memory"
              size={20}
              color={activeTab === 'memory' ? colors.primary : colors.onSurfaceVariant}
            />
            <Text
              variant="labelMedium"
              style={{ color: activeTab === 'memory' ? colors.primary : colors.onSurfaceVariant }}
            >
              记忆
            </Text>
          </TouchableOpacity>
        </View>

        <Divider />

        {/* 内容列表 */}
        {renderTabContent()}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: 50,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: 16,
    marginBottom: 12,
    paddingHorizontal: 12,
    borderRadius: 8,
    height: 40,
  },
  searchInput: {
    flex: 1,
    marginLeft: 8,
    fontSize: 16,
  },
  tabs: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  tab: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 8,
    marginHorizontal: 4,
    borderRadius: 8,
  },
  activeTab: {
    backgroundColor: 'rgba(34, 197, 94, 0.1)',
  },
  list: {
    flex: 1,
    paddingHorizontal: 16,
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  itemIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(34, 197, 94, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  itemContent: {
    flex: 1,
  },
  centerContent: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
});
