// HITL 人类请求卡片 - 对应 Desktop 的 MobileHumanRequestCard
// 支持 text/choice/confirmation/approval 四种类型

import React, { useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TextInput,
} from 'react-native';
import {
  Card,
  Text,
  Button,
  RadioButton,
  Divider,
  IconButton,
} from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import { HumanRequest, RiskLevel } from '@/types/hitl';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import Markdown from 'react-native-markdown-display';

export interface HumanRequestCardProps {
  request: HumanRequest;
  onRespond: (value: string) => void;
  onCancel?: () => void;
  disabled?: boolean;
}

// 风险等级配置（使用翻译键）
const riskConfig: Record<RiskLevel, { color: string; bgColor: string; icon: string; translationKey: string }> = {
  low: {
    color: '#22c55e',
    bgColor: '#dcfce7',
    icon: 'info',
    translationKey: 'hitl.riskLow',
  },
  medium: {
    color: '#f59e0b',
    bgColor: '#fef3c7',
    icon: 'warning',
    translationKey: 'hitl.riskMedium',
  },
  high: {
    color: '#ef4444',
    bgColor: '#fee2e2',
    icon: 'error',
    translationKey: 'hitl.riskHigh',
  },
  critical: {
    color: '#dc2626',
    bgColor: '#fecaca',
    icon: 'report',
    translationKey: 'hitl.riskCritical',
  },
};

export function HumanRequestCard({
  request,
  onRespond,
  onCancel,
  disabled = false,
}: HumanRequestCardProps) {
  const { t } = useTranslation();
  const { colors, isDark } = useTheme();
  const [value, setValue] = useState(request.default_value || '');
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 解析上下文
  const context = typeof request.context === 'object' ? request.context : null;
  const riskLevel = context?.risk_level || 'low';
  const risk = riskConfig[riskLevel];
  const isHighRisk = riskLevel === 'high' || riskLevel === 'critical';

  // 提交响应
  const handleSubmit = useCallback((responseValue: string) => {
    setIsSubmitting(true);
    onRespond(responseValue);
  }, [onRespond]);

  // 获取标题
  const getTitle = () => {
    switch (request.type) {
      case 'text':
        return t('hitl.titleText');
      case 'choice':
        return t('hitl.titleChoice');
      case 'confirmation':
        return t('hitl.titleConfirm');
      case 'approval':
        return t('hitl.titleApproval');
      default:
        return t('hitl.waiting');
    }
  };

  // 获取图标
  const getIcon = () => {
    switch (request.type) {
      case 'text':
        return 'chat';
      case 'choice':
        return 'list';
      case 'confirmation':
        return 'help';
      case 'approval':
        return 'gavel';
      default:
        return 'help-outline';
    }
  };

  // 渲染文本输入
  const renderTextInput = () => (
    <TextInput
      style={[
        styles.textInput,
        {
          backgroundColor: isDark ? colors.surfaceVariant : '#f3f4f6',
          color: colors.onSurface,
          borderColor: colors.outline,
        },
      ]}
      value={value}
      onChangeText={setValue}
      placeholder={t('chat_request.placeholder')}
      placeholderTextColor={colors.onSurfaceVariant}
      multiline
      numberOfLines={3}
      textAlignVertical="top"
      editable={!disabled && !isSubmitting}
    />
  );

  // 渲染选择项
  const renderChoice = () => (
    <RadioButton.Group onValueChange={setValue} value={value}>
      <View style={styles.choiceContainer}>
        {request.options?.map((option, index) => (
          <View
            key={index}
            style={[
              styles.choiceItem,
              {
                backgroundColor: value === option
                  ? colors.primaryContainer
                  : isDark
                  ? colors.surfaceVariant
                  : '#f3f4f6',
                borderColor: value === option ? colors.primary : 'transparent',
              },
            ]}
          >
            <RadioButton.Item
              label={option}
              value={option}
              style={styles.radioItem}
              labelStyle={{
                color: value === option ? colors.primary : colors.onSurface,
                fontWeight: value === option ? '600' : '400',
                fontSize: 14,
              }}
              color={colors.primary}
              disabled={disabled || isSubmitting}
            />
          </View>
        ))}
      </View>
    </RadioButton.Group>
  );

  // 渲染确认按钮
  const renderConfirmationButtons = () => (
    <View style={styles.buttonRow}>
      <Button
        mode="outlined"
        onPress={() => handleSubmit('no')}
        style={[styles.button, styles.cancelButton]}
        textColor={colors.onSurfaceVariant}
        disabled={isSubmitting}
      >
        {t('common.no')}
      </Button>
      <Button
        mode="contained"
        onPress={() => handleSubmit('yes')}
        style={styles.button}
        buttonColor={colors.primary}
        disabled={isSubmitting}
      >
        {t('common.yes')}
      </Button>



    </View>
  );

  // 渲染审批按钮
  const renderApprovalButtons = () => (
    <View style={styles.buttonRow}>
      <Button
        mode="outlined"
        onPress={() => handleSubmit('REJECTED')}
        style={[styles.button, styles.rejectButton]}
        textColor={colors.error}
        disabled={isSubmitting}
      >
        {t('hitl.reject')}
      </Button>
      <Button
        mode="contained"
        onPress={() => handleSubmit('APPROVED')}
        style={styles.button}
        buttonColor={isHighRisk ? colors.error : colors.primary}
        disabled={isSubmitting}
      >
        {isHighRisk ? `${t('hitl.approve')} (${t('hitl.riskHigh')})` : t('hitl.approve')}
      </Button>



    </View>
  );

  // 渲染提交按钮 (用于 text/choice)
  const renderSubmitButton = () => (
    <Button
      mode="contained"
      onPress={() => handleSubmit(value)}
      style={styles.submitButton}
      buttonColor={colors.primary}
      disabled={isSubmitting || disabled || !value.trim()}
      loading={isSubmitting}
    >
      {t('hitl.submit')}
    </Button>
  );

  return (
    <Card
      style={[
        styles.container,
        {
          borderLeftColor: risk.color,
          backgroundColor: isDark ? colors.surface : '#fff',
        },
        isHighRisk && styles.highRiskContainer,
      ]}
    >
      {/* 头部 */}
      <Card.Content style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={[styles.iconContainer, { backgroundColor: colors.primaryContainer }]}>
            <MaterialIcons name={getIcon()} size={20} color={colors.primary} />
          </View>
          <View>
            <Text style={[styles.title, { color: colors.onSurface }]}>
              {getTitle()}
            </Text>
            <Text style={[styles.subtitle, { color: colors.onSurfaceVariant }]}>
              {request.id.slice(0, 8)}...
            </Text>
          </View>
        </View>

        {/* 风险等级标签 */}
        <View style={[styles.riskBadge, { backgroundColor: risk.bgColor }]}>
          <MaterialIcons name={risk.icon as any} size={14} color={risk.color} />
          <Text style={[styles.riskText, { color: risk.color }]}>
            {t(risk.translationKey)}
          </Text>
        </View>
      </Card.Content>

      <Divider style={[styles.divider, { backgroundColor: colors.outline + '30' }]} />

      {/* 操作描述 */}
      {context?.action_description && (
        <Card.Content style={styles.actionSection}>
          <Text style={[styles.actionTitle, { color: colors.primary }]}>
            {context.action_description}
          </Text>
        </Card.Content>
      )}

      {/* 提示/问题 */}
      <Card.Content style={styles.promptSection}>
        <Text style={[styles.prompt, { color: colors.onSurface }]}>
          {request.prompt}
        </Text>
      </Card.Content>

      {/* 详细内容 (Markdown) */}
      {context?.details && (
        <Card.Content style={styles.detailsSection}>
          <View style={[styles.detailsContainer, { backgroundColor: isDark ? colors.surfaceVariant : '#f9fafb' }]}>
            <Markdown
              style={{
                body: { color: colors.onSurfaceVariant, fontSize: 13 },
                paragraph: { marginVertical: 4 },
                code_inline: {
                  backgroundColor: colors.surfaceVariant,
                  paddingHorizontal: 4,
                  borderRadius: 4,
                  fontFamily: 'monospace',
                },
              }}
            >
              {context.details}
            </Markdown>
          </View>
        </Card.Content>
      )}

      {/* 后果警告 */}
      {context?.consequences && (
        <Card.Content style={styles.consequencesSection}>
          <View style={[styles.consequencesContainer, { backgroundColor: risk.bgColor + '50' }]}>
            <MaterialIcons name="warning" size={18} color={risk.color} />
            <Text style={[styles.consequencesText, { color: risk.color }]}>
              {context.consequences}
            </Text>
          </View>
        </Card.Content>
      )}

      {/* 输入区域 */}
      <Card.Content style={styles.inputSection}>
        {request.type === 'text' && renderTextInput()}
        {request.type === 'choice' && renderChoice()}
      </Card.Content>

      {/* 按钮区域 */}
      <Card.Actions style={styles.actions}>
        {onCancel && (
          <Button
            mode="text"
            onPress={onCancel}
            textColor={colors.onSurfaceVariant}
            disabled={isSubmitting}
          >
            {t('hitl.skip')}
          </Button>
        )}
        
        {request.type === 'confirmation' && renderConfirmationButtons()}
        {request.type === 'approval' && renderApprovalButtons()}
        {(request.type === 'text' || request.type === 'choice') && renderSubmitButton()}
      </Card.Actions>
    </Card>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 12,
    marginVertical: 4,
    borderRadius: 12,
    borderLeftWidth: 4,
    elevation: 2,
  },
  highRiskContainer: {
    borderWidth: 1,
    borderColor: '#dc2626',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  iconContainer: {
    width: 32,
    height: 32,
    borderRadius: 8,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontSize: 15,
    fontWeight: '700',
  },
  subtitle: {
    fontSize: 10,
    marginTop: 0,
  },
  riskBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  riskText: {
    fontSize: 11,
    fontWeight: '600',
  },
  divider: {
    marginHorizontal: 12,
  },
  actionSection: {
    paddingTop: 8,
    paddingBottom: 0,
    paddingHorizontal: 12,
  },
  actionTitle: {
    fontSize: 14,
    fontWeight: '600',
  },
  promptSection: {
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  prompt: {
    fontSize: 14,
    lineHeight: 20,
  },
  detailsSection: {
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  detailsContainer: {
    padding: 8,
    borderRadius: 8,
  },
  consequencesSection: {
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  consequencesContainer: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    padding: 8,
    borderRadius: 8,
  },
  consequencesText: {
    flex: 1,
    fontSize: 12,
    lineHeight: 16,
  },
  inputSection: {
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  textInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 8,
    fontSize: 14,
    lineHeight: 20,
    minHeight: 60,
  },
  choiceContainer: {
    gap: 6,
  },
  choiceItem: {
    borderRadius: 8,
    borderWidth: 1,
  },
  radioItem: {
    paddingVertical: 4,
  },
  actions: {
    justifyContent: 'flex-end',
    padding: 12,
    paddingTop: 4,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
    flex: 1,
    justifyContent: 'flex-end',
  },
  button: {
    minWidth: 100,
    borderRadius: 8,
  },
  cancelButton: {
    borderColor: '#e5e7eb',
  },
  rejectButton: {
    borderColor: '#fca5a5',
  },
  submitButton: {
    minWidth: 120,
    borderRadius: 8,
  },
});
