import React, { useState } from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { List, Divider, Text, Card, Button, TextInput, Portal, Dialog } from 'react-native-paper';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@/theme';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Header } from '@/components/common/Header';
import { BASE_URL } from '@/constants/config';

export default function HelpScreen() {
  const { theme } = useTheme();
  const colors = theme.colors;
  const { t } = useTranslation();
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const FAQ_ITEMS = [
    {
      question: t('help.faq.q1'),
      answer: t('help.faq.a1'),
    },
    {
      question: t('help.faq.q2'),
      answer: t('help.faq.a2'),
    },
    {
      question: t('help.faq.q3'),
      answer: t('help.faq.a3'),
    },
    {
      question: t('help.faq.q4'),
      answer: t('help.faq.a4'),
    },
    {
      question: t('help.faq.q5'),
      answer: t('help.faq.a5'),
    },
  ];

  const toggleExpand = (index: number) => {
    setExpandedIndex(expandedIndex === index ? null : index);
  };

  const submitFeedback = async () => {
    if (!feedback.trim()) return;

    setIsSubmitting(true);
    // 模拟提交
    await new Promise((resolve) => setTimeout(resolve, 1000));
    setIsSubmitting(false);
    setShowFeedbackDialog(false);
    setFeedback('');
  };

  const openEmail = () => {
    Linking.openURL('mailto:support@develop-assistant.cn');
  };

  const openWebsite = () => {
    Linking.openURL(`${BASE_URL}/member/help`);
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <Header title={t('help.title')} showBack />
      <ScrollView>
        {/* Quick Actions */}
        <Card style={styles.quickActionsCard}>
          <Card.Content>
            <Text variant="titleMedium" style={{ marginBottom: 16, color: colors.onSurface }}>
              {t('help.quickActions.needHelp')}
            </Text>
            <View style={styles.actionButtons}>
              <Button
                mode="contained"
                icon="email"
                onPress={openEmail}
                style={styles.actionButton}
              >
                {t('help.quickActions.email')}
              </Button>
              <Button
                mode="outlined"
                icon="web"
                onPress={openWebsite}
                style={styles.actionButton}
              >
                {t('help.quickActions.helpCenter')}
              </Button>
            </View>
          </Card.Content>
        </Card>

        {/* FAQ */}
        <List.Section>
          <List.Subheader>{t('help.faq.title')}</List.Subheader>
          {FAQ_ITEMS.map((item, index) => (
            <React.Fragment key={index}>
              <List.Accordion
                title={item.question}
                expanded={expandedIndex === index}
                onPress={() => toggleExpand(index)}
                titleStyle={{ fontWeight: expandedIndex === index ? '600' : 'normal' }}
              >
                <View style={styles.answerContainer}>
                  <Text variant="bodyMedium" style={{ color: colors.onSurfaceVariant }}>
                    {item.answer}
                  </Text>
                </View>
              </List.Accordion>
              {index < FAQ_ITEMS.length - 1 && <Divider />}
            </React.Fragment>
          ))}
        </List.Section>

        <Divider />

        {/* Feedback */}
        <List.Section>
          <List.Subheader>{t('help.feedback.sectionTitle')}</List.Subheader>
          <List.Item
            title={t('help.feedback.submit')}
            description={t('help.feedback.description')}
            left={(props) => <List.Icon {...props} icon="message-text" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => setShowFeedbackDialog(true)}
          />
        </List.Section>

        <Divider />

        <View style={styles.bottomPadding} />
      </ScrollView>

      {/* Feedback Dialog */}
      <Portal>
        <Dialog visible={showFeedbackDialog} onDismiss={() => setShowFeedbackDialog(false)}>
          <Dialog.Title>{t('help.feedback.title')}</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label={t('help.feedback.label')}
              value={feedback}
              onChangeText={setFeedback}
              multiline
              numberOfLines={4}
              style={styles.feedbackInput}
            />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowFeedbackDialog(false)}>{t('help.feedback.cancel')}</Button>
            <Button onPress={submitFeedback} loading={isSubmitting} disabled={!feedback.trim()}>
              {t('help.feedback.confirm')}
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  quickActionsCard: {
    margin: 16,
    elevation: 0,
  },
  actionButtons: {
    flexDirection: 'row',
    gap: 12,
  },
  actionButton: {
    flex: 1,
  },
  answerContainer: {
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  feedbackInput: {
    marginTop: 8,
  },
  bottomPadding: {
    height: 40,
  },
});
