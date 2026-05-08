// 支付结果页面

import { View, StyleSheet } from 'react-native';
import { Text, Button, Avatar, useTheme } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { router } from '@/utils/navigation';
import { useTranslation } from 'react-i18next';
import { useRoute } from '@react-navigation/native';

export default function PayResultScreen() {
  const { t } = useTranslation();
  const route = useRoute<any>();
  const { colors } = useTheme();
  const params = route.params || {};
  const success = params.status === 'success';
  const amount = params.amount ? parseFloat(params.amount as string).toFixed(2) : '';
  const planName = (params.plan_name as string) || '';

  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        <Avatar.Icon
          size={120}
          icon={success ? 'check' : 'close'}
          style={[styles.icon, { backgroundColor: success ? colors.primary : colors.error }]}
        />

        <Text variant="headlineMedium" style={styles.title}>
          {success ? t('payResult.success') : t('payResult.failed')}
        </Text>

        {success ? (
          <>
            {amount && (
              <Text variant="displaySmall" style={[styles.amount, { color: colors.primary }]}>
                ¥{amount}
              </Text>
            )}
            <Text variant="bodyMedium" style={styles.message}>
              {planName ? t('payResult.subscribedPlan', { planName }) : t('payResult.subscribed')}
            </Text>
          </>
        ) : (
          <Text variant="bodyMedium" style={styles.message}>
            {t('payResult.errorMessage')}
          </Text>
        )}

        <View style={styles.buttons}>
          <Button
            mode="contained"
            onPress={() => router.replace('Main', { screen: 'profile' })}
            style={styles.button}
          >
            {t('payResult.viewBenefits')}
          </Button>
          <Button
            mode="outlined"
            onPress={() => router.replace('Main')}
            style={styles.button}
          >
            {t('payResult.backToHome')}
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
