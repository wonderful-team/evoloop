// Agent 执行步骤指示器

import React from 'react';
import { View, StyleSheet, Animated } from 'react-native';
import { Text, IconButton } from 'react-native-paper';
import { useTheme } from '@/theme';
import { AgentStep } from '@/types/agent';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

interface StepsIndicatorProps {
  steps: AgentStep[];
  currentStepId?: number;
  compact?: boolean;
}

export function StepsIndicator({ steps, currentStepId, compact = false }: StepsIndicatorProps) {
  const { colors } = useTheme();

  if (steps.length === 0) return null;

  // 获取步骤图标
  const getStepIcon = (step: AgentStep) => {
    switch (step.type) {
      case 'node':
        return 'account-tree';
      case 'tool':
        return 'build';
      case 'ai':
        return 'psychology';
      case 'skill':
        return 'zap';
      default:
        return 'circle';
    }
  };

  // 获取状态颜色
  const getStatusColor = (status: AgentStep['status']) => {
    switch (status) {
      case 'done':
      case 'success':
        return '#22c55e';
      case 'failed':
        return '#ef4444';
      case 'cancelled':
        return '#f59e0b';
      case 'running':
        return colors.primary;
      default:
        return colors.onSurfaceVariant;
    }
  };

  // 获取状态图标
  const getStatusIcon = (status: AgentStep['status']) => {
    switch (status) {
      case 'done':
      case 'success':
        return 'check-circle';
      case 'failed':
        return 'error';
      case 'cancelled':
        return 'cancel';
      case 'running':
        return 'sync';
      default:
        return 'radio-button-unchecked';
    }
  };

  // 简化版
  if (compact) {
    const runningStep = steps.find(s => s.status === 'running');
    if (!runningStep) return null;

    return (
      <View style={[styles.compactContainer, { backgroundColor: colors.primaryContainer }]}>
        <MaterialIcons name="sync" size={16} color={colors.primary} style={styles.rotatingIcon} />
        <Text style={[styles.compactText, { color: colors.primary }]} numberOfLines={1}>
          {runningStep.name}
        </Text>
      </View>
    );
  }

  // 完整版 - 只显示最近几个步骤
  const recentSteps = steps.slice(-5);

  return (
    <View style={[styles.container, { backgroundColor: colors.surfaceVariant }]}>
      <Text style={[styles.title, { color: colors.onSurface }]}>执行步骤</Text>
      
      {recentSteps.map((step, index) => {
        const isCurrent = step.id === currentStepId;
        const statusColor = getStatusColor(step.status);
        
        return (
          <View 
            key={step.id} 
            style={[
              styles.stepItem,
              isCurrent && { backgroundColor: colors.primaryContainer + '50' },
            ]}
          >
            {/* 连接线和图标 */}
            <View style={styles.stepLeft}>
              <View 
                style={[
                  styles.stepIconContainer, 
                  { backgroundColor: statusColor + '20' },
                ]}
              >
                <MaterialIcons
                  name={getStepIcon(step)}
                  size={14}
                  color={statusColor}
                />
              </View>
              
              {index < recentSteps.length - 1 && (
                <View style={[styles.stepLine, { backgroundColor: colors.outline + '30' }]} />
              )}
            </View>

            {/* 内容 */}
            <View style={styles.stepContent}>
              <View style={styles.stepHeader}>
                <Text 
                  style={[
                    styles.stepName, 
                    { color: isCurrent ? colors.primary : colors.onSurface },
                  ]}
                >
                  {step.name}
                </Text>
                
                <MaterialIcons
                  name={getStatusIcon(step.status)}
                  size={16}
                  color={statusColor}
                />
              </View>

              {step.input && (
                <Text style={[styles.stepInput, { color: colors.onSurfaceVariant }]} numberOfLines={1}>
                  输入: {JSON.stringify(step.input).slice(0, 50)}
                </Text>
              )}

              {step.output && step.status === 'done' && (
                <Text style={[styles.stepOutput, { color: colors.onSurfaceVariant }]} numberOfLines={2}>
                  {step.output.slice(0, 100)}
                </Text>
              )}

              {step.time && (
                <Text style={[styles.stepTime, { color: colors.onSurfaceVariant }]}>
                  {step.time}
                </Text>
              )}
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginVertical: 8,
    borderRadius: 12,
    padding: 12,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 12,
  },
  stepItem: {
    flexDirection: 'row',
    paddingVertical: 8,
    borderRadius: 8,
  },
  stepLeft: {
    alignItems: 'center',
    width: 28,
  },
  stepIconContainer: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  stepLine: {
    width: 2,
    flex: 1,
    marginVertical: 4,
  },
  stepContent: {
    flex: 1,
    marginLeft: 12,
  },
  stepHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stepName: {
    fontSize: 14,
    fontWeight: '500',
  },
  stepInput: {
    fontSize: 11,
    marginTop: 4,
    fontFamily: 'monospace',
  },
  stepOutput: {
    fontSize: 12,
    marginTop: 4,
  },
  stepTime: {
    fontSize: 11,
    marginTop: 4,
  },
  // 简化版样式
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    alignSelf: 'flex-start',
    gap: 6,
  },
  compactText: {
    fontSize: 12,
    fontWeight: '500',
  },
  rotatingIcon: {
    // 可以添加旋转动画
  },
});
