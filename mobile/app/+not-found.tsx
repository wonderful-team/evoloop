// 404 页面

import { View, StyleSheet } from 'react-native';
import { Text, Button } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from 'expo-router';

export default function NotFoundScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Text variant="displayLarge" style={styles.code}>
          404
        </Text>
        <Text variant="headlineMedium" style={styles.title}>
          页面未找到
        </Text>
        <Text variant="bodyMedium" style={styles.message}>
          您访问的页面不存在或已被移除
        </Text>
        <Button mode="contained" onPress={() => router.replace('/(main)')}>
          返回首页
        </Button>
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
  code: {
    fontWeight: 'bold',
    color: '#0066FF',
    marginBottom: 16,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  message: {
    opacity: 0.7,
    marginBottom: 32,
  },
});
