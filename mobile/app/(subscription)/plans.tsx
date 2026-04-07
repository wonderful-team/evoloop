// 订阅套餐列表页面

import { View, StyleSheet, ScrollView } from 'react-native';
import { Text, Card, Button, Chip } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { router } from 'expo-router';

export default function PlansScreen() {
  const { t } = useTranslation();
  
  const handleSubscribe = (planId: number) => {
    // TODO: 跳转到支付确认页
    router.push('/(subscription)/pay-confirm');
  };
  
  return (
    <SafeAreaView style={styles.container}>
      <ScrollView style={styles.content}>
        <Text variant="headlineMedium" style={styles.title}>
          选择会员方案
        </Text>
        <Text variant="bodyMedium" style={styles.subtitle}>
          解锁更多 AI 能力，提升开发效率
        </Text>
        
        {/* TODO: 从 API 获取套餐列表 */}
        <Card style={styles.planCard}>
          <Card.Content>
            <View style={styles.planHeader}>
              <Text variant="titleLarge">免费版</Text>
              <Chip>当前方案</Chip>
            </View>
            <Text variant="displaySmall" style={styles.price}>¥0</Text>
            <Text variant="bodyMedium" style={styles.period}>永久免费</Text>
            
            <View style={styles.benefits}>
              <Text style={styles.benefitItem}>• 每月 50 次 AI 调用</Text>
              <Text style={styles.benefitItem}>• 1 个项目</Text>
              <Text style={styles.benefitItem}>• 基础模型</Text>
            </View>
          </Card.Content>
        </Card>
        
        <Card style={[styles.planCard, styles.recommendedCard]}>
          <Card.Content>
            <View style={styles.planHeader}>
              <Text variant="titleLarge">极客版</Text>
              <Chip icon="star" selectedColor="#0066FF">推荐</Chip>
            </View>
            <Text variant="displaySmall" style={styles.price}>¥99</Text>
            <Text variant="bodyMedium" style={styles.period}>/月</Text>
            
            <View style={styles.benefits}>
              <Text style={styles.benefitItem}>• 每月 1000 次 AI 调用</Text>
              <Text style={styles.benefitItem}>• 10 个项目</Text>
              <Text style={styles.benefitItem}>• 语音对话</Text>
              <Text style={styles.benefitItem}>• 高级模型</Text>
            </View>
          </Card.Content>
          <Card.Actions>
            <Button mode="contained" onPress={() => handleSubscribe(2)} style={styles.subscribeButton}>
              立即订阅
            </Button>
          </Card.Actions>
        </Card>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    flex: 1,
    padding: 16,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  subtitle: {
    opacity: 0.7,
    marginBottom: 24,
  },
  planCard: {
    marginBottom: 16,
  },
  recommendedCard: {
    borderColor: '#0066FF',
    borderWidth: 2,
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  price: {
    fontWeight: 'bold',
    color: '#0066FF',
  },
  period: {
    opacity: 0.6,
    marginBottom: 16,
  },
  benefits: {
    marginTop: 8,
  },
  benefitItem: {
    marginVertical: 4,
    fontSize: 14,
  },
  subscribeButton: {
    flex: 1,
  },
});
