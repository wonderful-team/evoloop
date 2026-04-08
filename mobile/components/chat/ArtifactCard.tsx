// Artifact 展示卡片

import React from 'react';
import { View, StyleSheet, TouchableOpacity, ScrollView } from 'react-native';
import { Card, Text, IconButton, Button, Chip } from 'react-native-paper';
import { useTheme } from '@/theme';
import { Artifact, TestReportArtifact, CodeFileArtifact } from '@/types/artifact';
import { MaterialIcons } from '@expo/vector-icons';
import Markdown from 'react-native-markdown-display';

interface ArtifactCardProps {
  artifact: Artifact;
  onView?: (artifact: Artifact) => void;
  onDownload?: (artifact: Artifact) => void;
}

export function ArtifactCard({ artifact, onView, onDownload }: ArtifactCardProps) {
  const { colors } = useTheme();

  // 获取 Artifact 图标
  const getArtifactIcon = () => {
    switch (artifact.type) {
      case 'test_report':
        return 'assignment-turned-in';
      case 'code_file':
        return 'code';
      case 'document':
        return 'description';
      case 'requirement_analysis':
        return 'analytics';
      case 'diff':
        return 'difference';
      default:
        return 'insert-drive-file';
    }
  };

  // 获取 Artifact 颜色
  const getArtifactColor = () => {
    switch (artifact.type) {
      case 'test_report':
        return '#22c55e';
      case 'code_file':
        return '#3b82f6';
      case 'document':
        return '#f59e0b';
      case 'requirement_analysis':
        return '#8b5cf6';
      case 'diff':
        return '#ef4444';
      default:
        return colors.primary;
    }
  };

  // 渲染测试报告
  const renderTestReport = (data: TestReportArtifact['data']) => {
    const passRate = data.total_tests > 0 
      ? Math.round((data.passed / data.total_tests) * 100) 
      : 0;

    return (
      <View style={styles.testReportContainer}>
        <View style={styles.testStats}>
          <View style={[styles.statItem, { backgroundColor: '#dcfce7' }]}>
            <Text style={[styles.statValue, { color: '#16a34a' }]}>{data.passed}</Text>
            <Text style={[styles.statLabel, { color: '#16a34a' }]}>通过</Text>
          </View>
          <View style={[styles.statItem, { backgroundColor: '#fee2e2' }]}>
            <Text style={[styles.statValue, { color: '#dc2626' }]}>{data.failed}</Text>
            <Text style={[styles.statLabel, { color: '#dc2626' }]}>失败</Text>
          </View>
          <View style={[styles.statItem, { backgroundColor: '#f3f4f6' }]}>
            <Text style={[styles.statValue, { color: '#6b7280' }]}>{data.skipped}</Text>
            <Text style={[styles.statLabel, { color: '#6b7280' }]}>跳过</Text>
          </View>
        </View>
        
        <View style={styles.passRateContainer}>
          <View style={[styles.passRateBar, { backgroundColor: '#e5e7eb' }]}>
            <View 
              style={[
                styles.passRateFill, 
                { 
                  backgroundColor: passRate >= 80 ? '#22c55e' : passRate >= 50 ? '#f59e0b' : '#ef4444',
                  width: `${passRate}%`,
                }
              ]} 
            />
          </View>
          <Text style={styles.passRateText}>{passRate}% 通过率</Text>
        </View>

        {data.summary && (
          <Text style={[styles.summary, { color: colors.onSurfaceVariant }]}>
            {data.summary}
          </Text>
        )}
      </View>
    );
  };

  // 渲染代码文件
  const renderCodeFile = (data: CodeFileArtifact['data']) => {
    return (
      <View style={styles.codeFileContainer}>
        <View style={[styles.codeHeader, { backgroundColor: colors.surfaceVariant }]}>
          <MaterialIcons name="code" size={16} color={colors.onSurfaceVariant} />
          <Text style={[styles.codePath, { color: colors.onSurfaceVariant }]} numberOfLines={1}>
            {data.path}
          </Text>
          <Text style={[styles.codeLanguage, { color: colors.outline }]}>
            {data.language}
          </Text>
        </View>
        
        {data.content && (
          <ScrollView style={styles.codePreview} horizontal>
            <Markdown
              style={{
                body: { color: colors.onSurface, fontSize: 12, fontFamily: 'monospace' },
                code_block: { backgroundColor: 'transparent' },
              }}
            >
              {`
\`\`\`${data.language}
${data.content.slice(0, 500)}${data.content.length > 500 ? '...' : ''}
\`\`\`
`}
            </Markdown>
          </ScrollView>
        )}
      </View>
    );
  };

  // 渲染内容
  const renderContent = () => {
    switch (artifact.type) {
      case 'test_report':
        return renderTestReport((artifact as TestReportArtifact).data);
      case 'code_file':
        return renderCodeFile((artifact as CodeFileArtifact).data);
      default:
        return (
          <Text style={{ color: colors.onSurfaceVariant }}>
            点击查看详情
          </Text>
        );
    }
  };

  const color = getArtifactColor();

  return (
    <Card style={[styles.container, { borderLeftColor: color }]}>
      <Card.Content>
        {/* 头部 */}
        <View style={styles.header}>
          <View style={[styles.iconContainer, { backgroundColor: color + '20' }]}>
            <MaterialIcons name={getArtifactIcon()} size={24} color={color} />
          </View>
          
          <View style={styles.headerContent}>
            <Text style={[styles.title, { color: colors.onSurface }]} numberOfLines={1}>
              {artifact.name}
            </Text>
            <Chip style={styles.typeChip} textStyle={{ fontSize: 10 }}>
              {artifact.type}
            </Chip>
          </View>
          
          {artifact.status === 'generating' && (
            <IconButton icon="loading" size={20} iconColor={colors.primary} />
          )}
        </View>

        {/* 内容 */}
        {renderContent()}
      </Card.Content>
      
      <Card.Actions style={styles.actions}>
        <Button
          mode="text"
          onPress={() => onView?.(artifact)}
          icon="eye"
          compact
        >
          查看
        </Button>
        <Button
          mode="text"
          onPress={() => onDownload?.(artifact)}
          icon="download"
          compact
        >
          下载
        </Button>
      </Card.Actions>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginVertical: 8,
    borderLeftWidth: 4,
    borderRadius: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 12,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  headerContent: {
    flex: 1,
  },
  title: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  typeChip: {
    alignSelf: 'flex-start',
    height: 24,
  },
  actions: {
    justifyContent: 'flex-end',
    paddingHorizontal: 8,
  },
  // 测试报告样式
  testReportContainer: {
    marginTop: 8,
  },
  testStats: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
  },
  statItem: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 8,
    borderRadius: 8,
  },
  statValue: {
    fontSize: 20,
    fontWeight: '700',
  },
  statLabel: {
    fontSize: 12,
    marginTop: 2,
  },
  passRateContainer: {
    marginBottom: 12,
  },
  passRateBar: {
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
    marginBottom: 4,
  },
  passRateFill: {
    height: '100%',
    borderRadius: 4,
  },
  passRateText: {
    fontSize: 12,
    textAlign: 'center',
  },
  summary: {
    fontSize: 13,
    lineHeight: 18,
  },
  // 代码文件样式
  codeFileContainer: {
    marginTop: 8,
    borderRadius: 8,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#e5e7eb',
  },
  codeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    gap: 8,
  },
  codePath: {
    flex: 1,
    fontSize: 12,
    fontFamily: 'monospace',
  },
  codeLanguage: {
    fontSize: 11,
    textTransform: 'uppercase',
  },
  codePreview: {
    padding: 12,
    maxHeight: 200,
  },
});
