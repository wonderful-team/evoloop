// Agent 思考卡片

import React from 'react';
import { View, StyleSheet } from 'react-native';
import { Card, Text } from 'react-native-paper';
import { useTheme } from '@/theme';
import { AgentThought, ThoughtType } from '@/types/agent';
import { SkillMatchThought } from '@/types/skill';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';

interface ThoughtCardProps {
  thought: AgentThought | SkillMatchThought;
}

export function ThoughtCard({ thought }: ThoughtCardProps) {
  const { colors } = useTheme();

  // 获取图标
  const getIcon = (type: ThoughtType) => {
    switch (type) {
      case 'intent':
        return 'psychology';
      case 'skill_match':
        return 'zap';
      case 'optimization':
        return 'lightbulb';
      case 'planning':
        return 'account-tree';
      case 'reflection':
        return 'refresh';
      default:
        return 'psychology-alt';
    }
  };

  // 获取颜色
  const getColor = (type: ThoughtType) => {
    switch (type) {
      case 'intent':
        return { main: '#3b82f6', bg: '#dbeafe' };
      case 'skill_match':
        return { main: '#f59e0b', bg: '#fef3c7' };
      case 'optimization':
        return { main: '#22c55e', bg: '#dcfce7' };
      case 'planning':
        return { main: '#8b5cf6', bg: '#ede9fe' };
      case 'reflection':
        return { main: '#ec4899', bg: '#fce7f3' };
      default:
        return { main: colors.primary, bg: colors.primaryContainer };
    }
  };

  // 渲染技能匹配内容
  const renderSkillMatchContent = (content: SkillMatchThought['content']) => {
    return (
      <View style={styles.skillMatchContainer}>
        {content.matched_skills.map((skill, index) => (
          <View 
            key={index} 
            style={[styles.skillItem, { backgroundColor: colors.surface }]}
          >
            <View style={styles.skillHeader}>
              <Text style={[styles.skillName, { color: colors.onSurface }]}>
                {skill.skill_name}
              </Text>
              <View 
                style={[
                  styles.confidenceBadge, 
                  { 
                    backgroundColor: skill.confidence > 0.8 
                      ? '#dcfce7' 
                      : skill.confidence > 0.5 
                        ? '#fef3c7' 
                        : '#fee2e2',
                  }
                ]}
              >
                <Text 
                  style={{ 
                    fontSize: 11, 
                    color: skill.confidence > 0.8 
                      ? '#16a34a' 
                      : skill.confidence > 0.5 
                        ? '#d97706' 
                        : '#dc2626',
                  }}
                >
                  {Math.round(skill.confidence * 100)}%
                </Text>
              </View>
            </View>
            
            {skill.description && (
              <Text style={[styles.skillDesc, { color: colors.onSurfaceVariant }]} numberOfLines={2}>
                {skill.description}
              </Text>
            )}
          </View>
        ))}
      </View>
    );
  };

  // 渲染普通思考内容
  const renderContent = () => {
    if (thought.type === 'thought' && thought.thought_type === 'skill_match') {
      return renderSkillMatchContent((thought as SkillMatchThought).content);
    }

    if (typeof thought.content === 'string') {
      return (
        <Text style={[styles.contentText, { color: colors.onSurfaceVariant }]}>
          {thought.content}
        </Text>
      );
    }

    return (
      <View style={styles.objectContent}>
        {Object.entries(thought.content).map(([key, value]) => {
          if (key === 'type' || key === 'thought_type') return null;
          return (
            <View key={key} style={styles.objectItem}>
              <Text style={[styles.objectKey, { color: colors.onSurfaceVariant }]}>
                {key}:
              </Text>
              <Text 
                style={[styles.objectValue, { color: colors.onSurface }]} 
                numberOfLines={2}
              >
                {typeof value === 'object' ? JSON.stringify(value) : String(value)}
              </Text>
            </View>
          );
        })}
      </View>
    );
  };

  const color = getColor(thought.thought_type);

  return (
    <Card style={[styles.container, { backgroundColor: color.bg + '40' }]}>
      <Card.Content>
        <View style={styles.header}>
          <View style={[styles.iconContainer, { backgroundColor: color.bg }]}>
            <MaterialIcons name={getIcon(thought.thought_type)} size={18} color={color.main} />
          </View>
          
          <View style={styles.headerContent}>
            <Text style={[styles.title, { color: color.main }]}>
              {thought.title}
            </Text>
          </View>

          {thought.confidence !== undefined && (
            <Text style={[styles.confidence, { color: color.main }]}>
              {Math.round(thought.confidence * 100)}%
            </Text>
          )}
        </View>

        {renderContent()}
      </Card.Content>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 16,
    marginVertical: 6,
    borderRadius: 12,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  iconContainer: {
    width: 32,
    height: 32,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  headerContent: {
    flex: 1,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
  },
  confidence: {
    fontSize: 12,
    fontWeight: '500',
  },
  contentText: {
    fontSize: 13,
    lineHeight: 18,
    marginLeft: 42,
  },
  objectContent: {
    marginLeft: 42,
  },
  objectItem: {
    flexDirection: 'row',
    marginVertical: 2,
  },
  objectKey: {
    fontSize: 12,
    width: 80,
  },
  objectValue: {
    flex: 1,
    fontSize: 12,
    fontFamily: 'monospace',
  },
  skillMatchContainer: {
    marginLeft: 42,
    gap: 8,
  },
  skillItem: {
    padding: 10,
    borderRadius: 8,
  },
  skillHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  skillName: {
    fontSize: 13,
    fontWeight: '600',
  },
  confidenceBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  skillDesc: {
    fontSize: 12,
    marginTop: 4,
  },
});
