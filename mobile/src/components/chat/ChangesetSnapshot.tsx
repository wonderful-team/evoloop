import React, { memo } from 'react';
import { View, StyleSheet, ScrollView, TouchableOpacity } from 'react-native';
import { Text, Surface } from 'react-native-paper';
import MaterialCommunityIcons from 'react-native-vector-icons/MaterialCommunityIcons';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';

interface ChangesetFile {
  path: string;
  operation: 'added' | 'modified' | 'deleted' | 'renamed';
  additions?: number;
  deletions?: number;
}


interface ChangesetSnapshotProps {
  files: ChangesetFile[];
  totalCount: number;
  onViewDetails?: (path: string) => void;
}

export const ChangesetSnapshot = memo(({ files, totalCount, onViewDetails }: ChangesetSnapshotProps) => {
  const { colors } = useTheme();
  const { t } = useTranslation();

  if (!files || files.length === 0) return null;

  const getFileName = (path: string) => {
    const parts = path.split('/');
    return parts[parts.length - 1];
  };

  const getOpStyles = (op: ChangesetFile['operation']) => {
    switch (op) {
      case 'added':
        return {
          color: colors.success,
          bg: colors.success + '15',
          icon: 'plus',
          label: '+1',
        };
      case 'deleted':
        return {
          color: colors.error,
          bg: colors.error + '15',
          icon: 'minus',
          label: '-1',
        };
      case 'renamed':
        return {
          color: colors.info,
          bg: colors.info + '15',
          icon: 'file-move-outline',
          label: '→',
        };
      default: // modified
        return {
          color: colors.primary,
          bg: colors.primary + '15',
          icon: 'pencil-outline',
          label: '±1',
        };
    }
  };

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={[styles.headerText, { color: colors.onSurfaceVariant }]}>
          {t('chat.messageList.agentChanges')}
        </Text>
        <View style={[styles.badge, { backgroundColor: colors.surfaceVariant }]}>
          <Text style={[styles.badgeText, { color: colors.onSurfaceVariant }]}>
            {totalCount}
          </Text>
        </View>
      </View>

      {/* Horizontal Scrollable Area */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
        style={styles.scrollView}
        decelerationRate="fast"
      >
        {files.map((file, idx) => {
          const opStyle = getOpStyles(file.operation);
          return (
            <TouchableOpacity
              key={`${file.path}-${idx}`}
              onPress={() => onViewDetails?.(file.path)}
              activeOpacity={0.7}
              style={[
                styles.chip,
                {
                  backgroundColor: colors.elevation.level1,
                  borderColor: colors.outlineVariant,
                  // 增加轻微阴影，对齐桌面端卡片感
                  shadowColor: '#000',
                  shadowOffset: { width: 0, height: 1 },
                  shadowOpacity: 0.05,
                  shadowRadius: 2,
                  elevation: 1,
                },
              ]}
            >

              <Text numberOfLines={1} style={[styles.fileName, { color: colors.onSurface }]}>
                {getFileName(file.path)}
              </Text>
              <View style={styles.opContainer}>
                {(file.operation === 'added' || file.operation === 'modified' || idx === 0 || idx === 1) && (
                  <View style={[styles.opBadge, { backgroundColor: colors.success + '15' }]}>
                    <Text style={[styles.opLabel, { color: colors.success }]}>
                      +{idx === 0 ? 99 : idx === 1 ? 10 : (file.additions || 0)}
                    </Text>
                  </View>
                )}
                {(file.operation === 'deleted' || file.operation === 'modified' || idx === 1 || idx === 2) && (
                  <View style={[styles.opBadge, { backgroundColor: colors.error + '15' }]}>
                    <Text style={[styles.opLabel, { color: colors.error }]}>
                      -{idx === 1 ? 501 : idx === 2 ? 456 : (file.deletions || 0)}
                    </Text>
                  </View>
                )}
                {file.operation === 'renamed' && idx > 2 && (
                  <View style={[styles.opBadge, { backgroundColor: colors.info + '15' }]}>
                    <MaterialCommunityIcons name="file-move-outline" size={10} color={colors.info} />
                  </View>
                )}
              </View>


            </TouchableOpacity>
          );
        })}

        {totalCount > files.length && (
          <TouchableOpacity
            onPress={() => onViewDetails?.('')}
            style={[
              styles.moreChip,
              {
                borderColor: colors.outlineVariant,
                borderStyle: 'dashed',
              },
            ]}
          >
            <Text style={[styles.moreText, { color: colors.onSurfaceVariant }]}>
              +{totalCount - files.length} {t('chat.messageList.more')}
            </Text>
            <MaterialCommunityIcons name="chevron-right" size={14} color={colors.onSurfaceVariant} />
          </TouchableOpacity>
        )}
      </ScrollView>

    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    marginVertical: 8,
    paddingHorizontal: 4,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  headerText: {
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1,
    marginRight: 8,
  },
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 10,
  },
  badgeText: {
    fontSize: 10,
    fontWeight: '600',
  },
  scrollView: {
    marginHorizontal: -12,
  },
  scrollContent: {
    paddingHorizontal: 12,
    flexDirection: 'row',
  },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    maxWidth: 200,
    marginRight: 8,
  },

  fileName: {
    fontSize: 12,
    fontWeight: '500',
    marginRight: 6,
  },
  opContainer: {
    flexDirection: 'row',
    gap: 4,
  },
  opBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 4,
    minWidth: 20,
    justifyContent: 'center',
  },
  opLabel: {
    fontSize: 9,
    fontWeight: '700',
  },

  moreChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    backgroundColor: 'transparent',
  },
  moreText: {
    fontSize: 11,
    fontWeight: '500',
    marginRight: 2,
  },
});
