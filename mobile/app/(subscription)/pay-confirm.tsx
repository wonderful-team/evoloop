// 支付确认页面

import { View, StyleSheet } from 'react-native';
import { Text, Button, Card, RadioButton } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useState } from 'react';
import { router } from 'expo-router';

export default function PayConfirmScreen() {
  const [paymentMethod, setPaymentMethod] = useState('wechat');
  const [loading, setLoading] = useState(false);
  
  const handlePay = async () => {
    setLoading(true);
    // TODO: 调用支付 API
    setTimeout(() => {
      setLoading(false);
      router.push('/(subscription)/pay-result');
    }, 1500);
  };
  
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Card style={styles.amountCard}>
          <Card.Content style={styles.amountContent}>
            <Text variant="bodyMedium" style={styles.amountLabel}>
              支付金额
            </Text>
            <Text variant="displayLarge" style={styles.amount}>
              ¥99.00
            </Text>
            <Text variant="bodyMedium" style={styles.planName}>
              EvoLoop 极客版 - 月费
            </Text>
          </Card.Content>
        </Card>
        
        <Card style={styles.paymentCard}>
          <Card.Content>
            <Text variant="titleMedium" style={styles.sectionTitle}>
              选择支付方式
            </Text>
            
            <RadioButton.Group
              onValueChange={value => setPaymentMethod(value)}
              value={paymentMethod}
            >
              <RadioButton.Item
                label="微信支付"
                value="wechat"
                left={() => (
                  <View style={[styles.paymentIcon, { backgroundColor: '#07C160' }]}>
                    <Text style={styles.paymentIconText}>微</Text>
                  </View>
                )}
              />
              <RadioButton.Item
                label="支付宝"
                value="alipay"
                left={() => (
                  <View style={[styles.paymentIcon, { backgroundColor: '#1677FF' }]}>
                    <Text style={styles.paymentIconText}>支</Text>
                  </View>
                )}
              />
            </RadioButton.Group>
          </Card.Content>
        </Card>
        
        <View style={styles.footer}>
          <Text variant="bodySmall" style={styles.agreement}>
            点击支付即表示您同意《服务协议》和《隐私政策》
          </Text>
          <Button
            mode="contained"
            onPress={handlePay}
            loading={loading}
            disabled={loading}
            style={styles.payButton}
            contentStyle={styles.payButtonContent}
          >
            立即支付
          </Button>
        </View>
      </View>
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
  amountCard: {
    marginBottom: 16,
  },
  amountContent: {
    alignItems: 'center',
    paddingVertical: 24,
  },
  amountLabel: {
    opacity: 0.6,
    marginBottom: 8,
  },
  amount: {
    fontWeight: 'bold',
    color: '#22C55E',
    marginBottom: 8,
  },
  planName: {
    opacity: 0.7,
  },
  paymentCard: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  paymentIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  paymentIconText: {
    color: 'white',
    fontWeight: 'bold',
  },
  footer: {
    marginTop: 'auto',
  },
  agreement: {
    textAlign: 'center',
    opacity: 0.6,
    marginBottom: 16,
  },
  payButton: {
    borderRadius: 8,
  },
  payButtonContent: {
    paddingVertical: 8,
  },
});
