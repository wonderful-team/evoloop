// 支付确认页面
// 支持真实订单创建、降级检测、微信支付 APP 支付

import { View, StyleSheet, Alert } from 'react-native';
import { Text, Button, Card, RadioButton, ActivityIndicator } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { router } from '@/utils/navigation';
import { useRoute } from '@react-navigation/native';
import { useSubscriptionPlans, useSubscription, useCreateOrder, useUpgradePrice } from '@/hooks/useSubscription';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { handleBenefitError } from '@/utils/subscriptionErrors';
import { WechatPay } from '@/services/payment/WechatPay';
import { useTranslation } from 'react-i18next';

// 支付方式类型
 type PaymentMethod = 'wechat';

export default function PayConfirmScreen() {
  const route = useRoute<any>();
  const { theme } = useTheme();
  const colors = theme.colors;
  const { t } = useTranslation();
  const params = route.params || {};
  const levelId = parseInt(params.level_id as string) || 0;
  
  // 支付方式
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('wechat');
  
  // 获取数据
  const { plans, isLoading: isLoadingPlans } = useSubscriptionPlans();
  const { detail, hasActiveSubscription } = useSubscription();
  const { createOrder, isLoading: isCreatingOrder } = useCreateOrder();
  const { priceInfo, isLoading: isLoadingPrice } = useUpgradePrice(levelId);
  
  // 查找当前套餐
  const selectedPlan = useMemo(() => {
    return plans.find(p => p.level_id === levelId);
  }, [plans, levelId]);
  
  // 计算实际支付金额
  const payAmount = useMemo(() => {
    if (priceInfo?.net_amount) {
      return parseFloat(priceInfo.net_amount);
    }
    return selectedPlan ? parseFloat(selectedPlan.price) : 0;
  }, [priceInfo, selectedPlan]);
  
  // 检查是否为升级
  const isUpgrade = useMemo(() => {
    return priceInfo?.is_upgrade === true;
  }, [priceInfo]);
  
  // 检查是否为降级
  const isDowngrade = useMemo(() => {
    if (!hasActiveSubscription || !detail || !selectedPlan) return false;
    const currentSort = detail.level_info?.sort ?? detail.level_id ?? 0;
    const targetSort = selectedPlan.benefits?.sort ?? selectedPlan.level_id ?? 0;
    return targetSort < currentSort;
  }, [hasActiveSubscription, detail, selectedPlan]);
  
  // 处理支付
  const handlePay = useCallback(async () => {
    if (!levelId) {
      Alert.alert(t('common.error.title'), t('payConfirm.invalidPlan'));
      return;
    }
    
    if (isDowngrade) {
      Alert.alert(t('payConfirm.cannotPurchase'), t('payConfirm.cannotPurchaseDesc'));
      return;
    }
    
    try {
      // 1. 创建订单
      const orderResult = await createOrder({
        level_id: levelId,
        auto_renew: 0,
        app_type: 'app',
      });
      
      if (!orderResult) {
        Alert.alert(t('payConfirm.orderFailed'), t('payConfirm.retryLater'));
        return;
      }
      
      // 2. 检查是否有支付数据
      if (!orderResult.pay_data) {
        Alert.alert(t('payConfirm.paymentParamError'), t('payConfirm.paymentParamErrorDesc'));
        return;
      }
      
      // 3. 调起微信支付
      const payResult = await WechatPay.pay(orderResult.pay_data);
      
      if (payResult.success) {
        // 支付成功，跳转到结果页
        router.push('PayResult', {
          order_id: orderResult.order_id,
          status: 'success',
          amount: payAmount.toFixed(2),
          plan_name: selectedPlan?.level_name || ''
        });
      } else {
        // 支付失败或取消
        if (payResult.errCode === -2) {
          // 用户取消，停留在当前页
          Alert.alert(t('payConfirm.paymentCancelled'), t('payConfirm.paymentCancelledDesc'));
        } else {
          // 支付失败
          Alert.alert(t('payConfirm.paymentFailed'), payResult.errStr || t('payConfirm.retryLater'));
        }
      }
    } catch (error: any) {
      console.error('Create order error:', error);
      
      // 处理权益错误（如降级购买被拒绝）
      if (error?.info?.code === 'BENEFIT_REQUIRED' || error?.code === 'BENEFIT_REQUIRED') {
        const errorInfo = handleBenefitError(error.info || error);
        Alert.alert(errorInfo.title, errorInfo.message);
        return;
      }
      
      // 降级购买错误
      if (error?.message?.includes('降级') || error?.message?.includes('到期')) {
        Alert.alert(t('payConfirm.cannotPurchase'), error.message || t('payConfirm.cannotPurchaseDesc'));
        return;
      }
      
      Alert.alert(t('payConfirm.orderFailed'), error?.message || t('payConfirm.retryLater'));
    }
  }, [levelId, isDowngrade, createOrder, t, selectedPlan, payAmount]);
  
  // 加载中
  if (isLoadingPlans || !selectedPlan) {
    return (
      <SafeAreaView style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color="#109C8F" />
        <Text style={styles.loadingText}>{t('payConfirm.loading')}</Text>
      </SafeAreaView>
    );
  }
  
  return (
    <SafeAreaView style={styles.container}>
      <View style={styles.content}>
        {/* 金额卡片 */}
        <Card style={styles.amountCard}>
          <Card.Content style={styles.amountContent}>
            <Text variant="bodyMedium" style={styles.amountLabel}>
              {isUpgrade ? t('payConfirm.upgradePayAmount') : t('payConfirm.payAmount')}
            </Text>
            <Text variant="displayLarge" style={styles.amount}>
              ¥{payAmount.toFixed(2)}
            </Text>
            <Text variant="bodyMedium" style={styles.planName}>
              {t('payConfirm.planName', { name: selectedPlan.level_name, days: selectedPlan.subscription_quota || 30 })}
            </Text>
            
            {/* 升级信息 */}
            {isUpgrade && priceInfo && (
              <View style={styles.upgradeInfo}>
                <View style={styles.upgradeRow}>
                  <Text style={styles.upgradeLabel}>{t('payConfirm.newAmount')}</Text>
                  <Text style={styles.upgradeValue}>¥{priceInfo.pay_amount}</Text>
                </View>
                <View style={styles.upgradeRow}>
                  <Text style={styles.upgradeLabel}>{t('payConfirm.refundAmount')}</Text>
                  <Text style={[styles.upgradeValue, styles.refundValue]}>-¥{priceInfo.refund_amount}</Text>
                </View>
                <View style={[styles.upgradeRow, styles.netRow]}>
                  <Text style={styles.upgradeLabel}>{t('payConfirm.actualAmount')}</Text>
                  <Text style={[styles.upgradeValue, styles.netValue]}>¥{priceInfo.net_amount}</Text>
                </View>
              </View>
            )}
            
            {/* 降级警告 */}
            {isDowngrade && (
              <View style={styles.downgradeWarning}>
                <MaterialIcons name="warning" size={20} color="#EF4444" />
                <Text style={styles.downgradeText}>
                  {t('payConfirm.downgradeWarning')}
                </Text>
              </View>
            )}
          </Card.Content>
        </Card>
        
        {/* 支付方式 */}
        <Card style={styles.paymentCard}>
          <Card.Content>
            <Text variant="titleMedium" style={styles.sectionTitle}>
              {t('payConfirm.selectPayment')}
            </Text>
            
            <RadioButton.Group
              onValueChange={(value) => setPaymentMethod(value as PaymentMethod)}
              value={paymentMethod}
            >
              <RadioButton.Item
                label={t('payConfirm.wechatPay')}
                value="wechat"
                disabled={isDowngrade}
                left={() => (
                  <View style={[styles.paymentIcon, { backgroundColor: '#07C160' }]}>
                    <MaterialIcons name="wechat" size={20} color="white" />
                  </View>
                )}
              />
            </RadioButton.Group>
          </Card.Content>
        </Card>
        
        {/* 权益预览 */}
        <Card style={styles.benefitsCard}>
          <Card.Content>
            <Text variant="titleMedium" style={styles.sectionTitle}>
              {t('payConfirm.benefits')}
            </Text>
            {selectedPlan.benefits?.ai_quota !== undefined && (
              <View style={styles.benefitItem}>
                <MaterialIcons name="chat" size={18} color="#109C8F" />
                <Text style={styles.benefitText}>
                  {t('payConfirm.aiQuota', { 
                    quota: selectedPlan.benefits.ai_quota === -1 
                      ? t('payConfirm.unlimited') 
                      : `${selectedPlan.benefits.ai_quota}${t('payConfirm.timesPerMonth')}` 
                  })}
                </Text>
              </View>
            )}
            {selectedPlan.benefits?.project_limit !== undefined && (
              <View style={styles.benefitItem}>
                <MaterialIcons name="folder" size={18} color="#109C8F" />
                <Text style={styles.benefitText}>
                  {t('payConfirm.projectCount', { 
                    count: selectedPlan.benefits.project_limit === -1 
                      ? t('payConfirm.unlimited') 
                      : `${selectedPlan.benefits.project_limit}${t('payConfirm.projectUnit')}` 
                  })}
                </Text>
              </View>
            )}
            {selectedPlan.benefits?.ai_advanced && (
              <View style={styles.benefitItem}>
                <MaterialIcons name="auto-awesome" size={18} color="#109C8F" />
                <Text style={styles.benefitText}>{t('payConfirm.advancedModels')}</Text>
              </View>
            )}
            {selectedPlan.benefits?.voice && (
              <View style={styles.benefitItem}>
                <MaterialIcons name="mic" size={18} color="#109C8F" />
                <Text style={styles.benefitText}>{t('payConfirm.voiceChat')}</Text>
              </View>
            )}
          </Card.Content>
        </Card>
        
        {/* 底部按钮 */}
        <View style={styles.footer}>
          <Text variant="bodySmall" style={styles.agreement}>
            {t('payConfirm.agreement')}
          </Text>
          <Button
            mode="contained"
            onPress={handlePay}
            loading={isCreatingOrder}
            disabled={isCreatingOrder || isDowngrade || isLoadingPrice}
            style={[styles.payButton, isDowngrade && styles.payButtonDisabled]}
            contentStyle={styles.payButtonContent}
            buttonColor={isDowngrade ? '#9CA3AF' : '#109C8F'}
          >
            {isDowngrade ? t('payConfirm.cannotPurchase') : isUpgrade ? t('payConfirm.confirmUpgrade') : t('payConfirm.payNow')}
          </Button>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F9FAFB',
  },
  content: {
    flex: 1,
    padding: 16,
  },
  center: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    marginTop: 12,
    opacity: 0.6,
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
    color: '#109C8F',
    marginBottom: 8,
  },
  planName: {
    opacity: 0.7,
  },
  upgradeInfo: {
    width: '100%',
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  upgradeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginVertical: 4,
  },
  upgradeLabel: {
    opacity: 0.7,
  },
  upgradeValue: {
    fontWeight: '500',
  },
  refundValue: {
    color: '#109C8F',
  },
  netRow: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
  },
  netValue: {
    fontWeight: 'bold',
    color: '#109C8F',
  },
  downgradeWarning: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 16,
    padding: 12,
    backgroundColor: '#FEE2E2',
    borderRadius: 8,
  },
  downgradeText: {
    marginLeft: 8,
    color: '#DC2626',
    fontWeight: '500',
  },
  paymentCard: {
    marginBottom: 16,
  },
  benefitsCard: {
    marginBottom: 16,
  },
  sectionTitle: {
    fontWeight: 'bold',
    marginBottom: 12,
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
  benefitItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 6,
  },
  benefitText: {
    marginLeft: 8,
    fontSize: 14,
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
  payButtonDisabled: {
    backgroundColor: '#9CA3AF',
  },
  payButtonContent: {
    paddingVertical: 8,
  },
});
