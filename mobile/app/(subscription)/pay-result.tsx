// 支付结果页面

import { View, StyleSheet } from 'react-native';
import { Text, Button, Avatar } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';

export default function PayResultScreen() {
  const success = true; // TODO: 从路由参数获取
  
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Avatar.Icon
          size={120}
          icon={success ? 'check' : 'close'}
          style={[styles.icon, { backgroundColor: success ? '#00C853' : '#FF3D00' }]}
        />
        
        <Text variant="headlineMedium" style={styles.title}>
          {success ? '支付成功' : '支付失败'}
        </Text>
        
        {success ? (
          <>
            <Text variant="displaySmall" style={styles.amount}>
              ¥99.00
            </Text>
            <Text variant="bodyMedium" style={styles.message}>
              您已成功订阅 EvoLoop 极客版
            </Text>
          </>
        ) : (
          <Text variant="bodyMedium" style={styles.message}>
            支付遇到问题，请重试或联系客服
          </Text>
        )}
        
        <View style={styles.buttons}>
          <Button
            mode="contained"
            onPress={() => router.replace('/(main)/profile')}
            style={styles.button}
          >
            查看权益
          </Button>
          <Button
            mode="outlined"
            onPress={() => router.replace('/(main)')}
            style={styles.button}
          >
            返回首页
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
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  icon: {
    marginBottom: 24,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 16,
  },
  amount: {
    fontWeight: 'bold',
    color: '#22C55E',
    marginBottom: 8,
  },
  message: {
    opacity: 0.7,
    textAlign: 'center',
    marginBottom: 48,
  },
  buttons: {
    width: '100%',
    maxWidth: 300,
  },
  button: {
    marginVertical: 8,
  },
});
