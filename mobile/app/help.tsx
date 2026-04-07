// 帮助与反馈页面

import React, { useState } from 'react';
import { View, StyleSheet, ScrollView, Linking } from 'react-native';
import { List, Divider, Text, Card, Button, TextInput, Portal, Dialog } from 'react-native-paper';
import { useTheme } from '@/components/ui/ThemeProvider';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';

const FAQ_ITEMS = [
  {
    question: '如何连接我的电脑？',
    answer: '在您的 Mac/Windows 电脑上下载并安装 EvoLoop 客户端，登录相同账号后即可自动连接。',
  },
  {
    question: '云端与本地模式的区别？',
    answer: '云端模式与运行在服务器上的 AI 交互，不依赖您的电脑。本地模式通过 AI 直接操作您的电脑，可以读取本地文件、运行终端命令。',
  },
  {
    question: '支持语音输入吗？',
    answer: '支持。点击麦克风图标即可开始说话，支持中文和英文指令。',
  },
  {
    question: '如何切换项目？',
    answer: '在首页点击项目名称，或进入项目列表页面选择要切换的项目。',
  },
  {
    question: '语音对话如何使用？',
    answer: '进入语音页面后，点击麦克风按钮开始录音，说话后松开即可发送语音。AI 会自动识别并回复。',
  },
];

export default function HelpScreen() {
  const { colors } = useTheme();
  const router = useRouter();
  const [expandedIndex, setExpandedIndex] = useState<number | null>(null);
  const [showFeedbackDialog, setShowFeedbackDialog] = useState(false);
  const [feedback, setFeedback] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

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
    Linking.openURL('https://evoloop.develop-assistant.cn/help');
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.colors.background }]}>
      <ScrollView>
        {/* 快速操作 */}
        <Card style={styles.quickActionsCard}>
          <Card.Content>
            <Text variant="titleMedium" style={{ marginBottom: 16, color: colors.colors.onSurface }}>
              需要帮助？
            </Text>
            <View style={styles.actionButtons}>
              <Button
                mode="contained"
                icon="email"
                onPress={openEmail}
                style={styles.actionButton}
              >
                邮件联系
              </Button>
              <Button
                mode="outlined"
                icon="web"
                onPress={openWebsite}
                style={styles.actionButton}
              >
                帮助中心
              </Button>
            </View>
          </Card.Content>
        </Card>

        {/* FAQ */}
        <List.Section>
          <List.Subheader>常见问题</List.Subheader>
          {FAQ_ITEMS.map((item, index) => (
            <React.Fragment key={index}>
              <List.Accordion
                title={item.question}
                expanded={expandedIndex === index}
                onPress={() => toggleExpand(index)}
                titleStyle={{ fontWeight: expandedIndex === index ? '600' : 'normal' }}
              >
                <View style={styles.answerContainer}>
                  <Text variant="bodyMedium" style={{ color: colors.colors.onSurfaceVariant }}>
                    {item.answer}
                  </Text>
                </View>
              </List.Accordion>
              {index < FAQ_ITEMS.length - 1 && <Divider />}
            </React.Fragment>
          ))}
        </List.Section>

        <Divider />

        {/* 反馈 */}
        <List.Section>
          <List.Subheader>反馈建议</List.Subheader>
          <List.Item
            title="提交反馈"
            description="告诉我们您的建议或遇到的问题"
            left={(props) => <List.Icon {...props} icon="message-text" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => setShowFeedbackDialog(true)}
          />
        </List.Section>

        <Divider />

        {/* 新手引导 */}
        <List.Section>
          <List.Subheader>新用户</List.Subheader>
          <List.Item
            title="查看新手引导"
            description="重新查看应用介绍和功能说明"
            left={(props) => <List.Icon {...props} icon="school" />}
            right={(props) => <List.Icon {...props} icon="chevron-right" />}
            onPress={() => router.push('/onboarding')}
          />
        </List.Section>

        <View style={styles.bottomPadding} />
      </ScrollView>

      {/* 反馈对话框 */}
      <Portal>
        <Dialog visible={showFeedbackDialog} onDismiss={() => setShowFeedbackDialog(false)}>
          <Dialog.Title>提交反馈</Dialog.Title>
          <Dialog.Content>
            <TextInput
              label="您的建议或问题"
              value={feedback}
              onChangeText={setFeedback}
              multiline
              numberOfLines={4}
              style={styles.feedbackInput}
            />
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowFeedbackDialog(false)}>取消</Button>
            <Button onPress={submitFeedback} loading={isSubmitting} disabled={!feedback.trim()}>
              提交
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
