// 订阅套餐列表页面
// 支持真实 API 数据、降级检测、当前套餐标记

import { View, StyleSheet, ScrollView, RefreshControl } from 'react-native';
import { Text, Card, Button, Chip, ActivityIndicator, Divider } from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { Header } from '@/components/common/Header';
import { router } from '@/utils/navigation';
import { useCallback, useMemo } from 'react';
import { useSubscriptionPlans, useSubscription, useIsDowngrade } from '@/hooks/useSubscription';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';

// 权益图标映射
const BENEFIT_ICONS: Record<string, string> = {
  ai_quota: 'chat',
  ai_advanced: 'auto-awesome',
  voice: 'mic',
  project_limit: 'folder',
  gantt: 'insert-chart',
  timesheet: 'schedule',
};

// 格式化价格显示
function formatPrice(price: string | number, freeLabel: string): string {
  const num = typeof price === 'string' ? parseFloat(price) : price;
  if (isNaN(num) || num === 0) return freeLabel;
  return `¥${num}`;
}

// 单个套餐卡片组件
interface PlanCardProps {
  plan: {
    level_id: number;
    level_name: string;
    price: string;
    market_price: string;
    subscription_quota: number;
    description?: string;
    benefits: Record<string, any>;
  };
  isCurrentPlan: boolean;
  isDowngrade: boolean;
  currentSort: number;
  targetSort: number;
  onSubscribe: (planId: number, isDowngrade: boolean) => void;
  isDark: boolean;
}

function PlanCard({ plan, isCurrentPlan, isDowngrade, currentSort, targetSort, onSubscribe, isDark }: PlanCardProps) {
  const { t } = useTranslation();

  // 降级卡片样式
  const cardStyle = useMemo(() => {
    if (isDowngrade) {
      return [styles.planCard, styles.downgradeCard];
    }
    if (plan.level_id === 20) { // 极客版推荐
      return [styles.planCard, styles.recommendedCard];
    }
    return styles.planCard;
  }, [isDowngrade, plan.level_id]);

  // 渲染权益列表
  const renderBenefits = () => {
    const benefits = plan.benefits || {};
    const items = [];
    
    // AI 额度
    if (benefits.ai_quota !== undefined) {
      const quota = benefits.ai_quota === -1 ? t('plans.unlimited') : `${benefits.ai_quota}${t('plans.timesPerMonth')}`;
      items.push({ icon: 'chat', text: t('plans.aiQuota', { quota }) });
    }
    
    // 项目数量
    if (benefits.project_limit !== undefined) {
      const limit = benefits.project_limit === -1 ? t('plans.unlimited') : `${benefits.project_limit}${t('plans.projectUnit')}`;
      items.push({ icon: 'folder', text: t('plans.projectCount', { limit }) });
    }
    
    // 高级模型
    if (benefits.ai_advanced) {
      items.push({ icon: 'auto-awesome', text: t('plans.advancedModels') });
    }
    
    // 语音
    if (benefits.voice) {
      items.push({ icon: 'mic', text: t('plans.voiceChat') });
    }
    
    // 甘特图
    if (benefits.gantt) {
      items.push({ icon: 'insert-chart', text: t('plans.ganttChart') });
    }
    
    // 工时表
    if (benefits.timesheet) {
      items.push({ icon: 'schedule', text: t('plans.timesheet') });
    }
    
    return items.map((item, index) => (
      <View key={index} style={styles.benefitRow}>
        <MaterialIcons 
          name={item.icon as any} 
          size={18} 
          color={isDowngrade ? '#9CA3AF' : '#109C8F'} 
          style={styles.benefitIcon} 
        />
        <Text style={[styles.benefitText, isDowngrade && styles.downgradeText]}>
          {item.text}
        </Text>
      </View>
    ));
  };

  // 渲染操作按钮/状态
  const renderAction = () => {
    if (isCurrentPlan) {
      return (
        <View style={styles.currentPlanBadge}>
          <MaterialIcons name="check-circle" size={20} color="#109C8F" />
          <Text style={styles.currentPlanText}>{t('plans.currentPlan')}</Text>
        </View>
      );
    }
    
    if (isDowngrade) {
      return (
        <View style={styles.downgradeInfo}>
          <MaterialIcons name="info-outline" size={18} color="#9CA3AF" />
          <Text style={styles.downgradeInfoText}>{t('plans.downgradeInfo')}</Text>
          <Text style={styles.downgradeSubText}>{t('plans.downgradeSub')}</Text>
        </View>
      );
    }
    
    return (
      <Button 
        mode="contained" 
        onPress={() => onSubscribe(plan.level_id, false)}
        style={styles.subscribeButton}
        buttonColor={plan.level_id === 20 ? '#109C8F' : undefined}
      >
        {t('plans.subscribeNow')}
      </Button>
    );
  };

  return (
    <Card style={cardStyle}>
      <Card.Content>
        <View style={styles.planHeader}>
          <View>
            <Text variant="titleLarge" style={isDowngrade && styles.downgradeTitle}>
              {plan.level_name}
            </Text>
            {plan.level_id === 20 && !isDowngrade && (
              <Chip icon="star" style={styles.recommendedChip} textStyle={{ color: '#109C8F' }}>
                {t('plans.recommended')}
              </Chip>
            )}
          </View>
          {isDowngrade && (
            <Chip style={styles.downgradeChip}>{t('plans.cannotDowngrade')}</Chip>
          )}
        </View>
        
        <View style={styles.priceRow}>
          <Text variant="displaySmall" style={[styles.price, isDowngrade && styles.downgradePrice]}>
            {formatPrice(plan.price, t('plans.free'))}
          </Text>
          {parseFloat(plan.market_price) > parseFloat(plan.price) && (
            <Text style={styles.marketPrice}>¥{plan.market_price}</Text>
          )}
        </View>
        <Text variant="bodyMedium" style={[styles.period, isDowngrade && styles.downgradeText]}>
          {t('plans.period', { days: plan.subscription_quota || 30 })}
        </Text>
        
        <Divider style={styles.divider} />
        
        <View style={styles.benefits}>
          {renderBenefits()}
        </View>
      </Card.Content>
      <Card.Actions style={styles.cardActions}>
        {renderAction()}
      </Card.Actions>
    </Card>
  );
}

// 主页面
export default function PlansScreen() {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  
  // 获取订阅数据
  const { plans, isLoading: isLoadingPlans, refresh: refreshPlans } = useSubscriptionPlans();
  const { detail, hasActiveSubscription, isLoading: isLoadingDetail, refreshAll } = useSubscription();
  
  // 当前选中的套餐（用于降级检测）
  const currentLevelId = detail?.level_id ?? 0;
  const currentSort = detail?.level_info?.sort ?? detail?.level_id ?? 0;
  
  // 处理订阅
  const handleSubscribe = useCallback((planId: number, isDowngrade: boolean) => {
    if (isDowngrade) {
      // 降级不允许购买
      return;
    }
    
    // 跳转到支付确认页，传递套餐信息
    router.push('PayConfirm', { level_id: planId.toString() });
  }, []);
  
  // 下拉刷新
  const handleRefresh = useCallback(async () => {
    await Promise.all([refreshPlans(), refreshAll()]);
  }, [refreshPlans, refreshAll]);

  // 按 sort 排序套餐 (必须放在任何条件返回之前)
  const sortedPlans = useMemo(() => {
    return [...plans].sort((a, b) => {
      const sortA = a.benefits?.sort ?? a.level_id;
      const sortB = b.benefits?.sort ?? b.level_id;
      return sortA - sortB;
    });
  }, [plans]);
  
  // 加载状态
  if (isLoadingPlans || isLoadingDetail) {
    return (
      <SafeAreaView style={[styles.container, styles.center]}>
        <ActivityIndicator size="large" color="#109C8F" />
        <Text style={styles.loadingText}>{t('plans.loading')}</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <Header title={t('plans.title')} showBack />
      <ScrollView
        style={styles.content}
        refreshControl={
          <RefreshControl refreshing={isLoadingPlans} onRefresh={handleRefresh} />
        }
      >
        {/* 头部信息 */}
        <View style={styles.header}>
          <Text variant="bodyMedium" style={styles.subtitle}>
            {t('plans.unlockMore')}
          </Text>

          {hasActiveSubscription && (
            <View style={styles.currentSubscription}>
              <MaterialIcons name="verified" size={20} color="#109C8F" />
              <Text style={styles.currentSubscriptionText}>
                {t('plans.currentSubscription', { name: detail?.level_name, days: detail?.remaining_days })}
              </Text>
            </View>
          )}
        </View>
        
        {/* 套餐列表 */}
        {sortedPlans.length === 0 ? (
          <View style={styles.emptyState}>
            <MaterialIcons name="error-outline" size={48} color="#9CA3AF" />
            <Text style={styles.emptyText}>{t('plans.noPlans')}</Text>
          </View>
        ) : (
          sortedPlans.map((plan) => {
            // 判断是否为当前套餐
            const isCurrentPlan = hasActiveSubscription && currentLevelId === plan.level_id;
            
            // 判断是否为降级
            const targetSort = plan.benefits?.sort ?? plan.level_id;
            const isDowngrade = hasActiveSubscription && targetSort < currentSort && !isCurrentPlan;
            
            return (
              <PlanCard
                key={plan.level_id}
                plan={plan}
                isCurrentPlan={isCurrentPlan}
                isDowngrade={isDowngrade}
                currentSort={currentSort}
                targetSort={targetSort}
                onSubscribe={handleSubscribe}
                isDark={isDark}
              />
            );
          })
        )}
        
        {/* 底部说明 */}
        <View style={styles.footer}>
          <Text style={styles.footerText}>
            {t('plans.autoRenewal')}
          </Text>
        </View>
      </ScrollView>
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
  header: {
    marginBottom: 24,
  },
  title: {
    fontWeight: 'bold',
    marginBottom: 8,
  },
  subtitle: {
    opacity: 0.7,
  },
  currentSubscription: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 12,
    padding: 12,
    backgroundColor: '#E6F4F3',
    borderRadius: 8,
  },
  currentSubscriptionText: {
    marginLeft: 8,
    color: '#0A3D38',
    fontWeight: '500',
  },
  planCard: {
    marginBottom: 16,
    backgroundColor: '#FFFFFF',
  },
  recommendedCard: {
    borderColor: '#109C8F',
    borderWidth: 2,
  },
  downgradeCard: {
    opacity: 0.7,
    backgroundColor: '#F3F4F6',
  },
  planHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  downgradeTitle: {
    color: '#6B7280',
  },
  recommendedChip: {
    backgroundColor: '#E6F4F3',
    marginTop: 4,
  },
  downgradeChip: {
    backgroundColor: '#E5E7EB',
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
  },
  price: {
    fontWeight: 'bold',
    color: '#109C8F',
  },
  downgradePrice: {
    color: '#9CA3AF',
  },
  marketPrice: {
    marginLeft: 8,
    textDecorationLine: 'line-through',
    opacity: 0.5,
    fontSize: 14,
  },
  period: {
    opacity: 0.6,
    marginBottom: 12,
  },
  divider: {
    marginVertical: 12,
  },
  benefits: {
    marginTop: 4,
  },
  benefitRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: 6,
  },
  benefitIcon: {
    marginRight: 8,
  },
  benefitText: {
    fontSize: 14,
  },
  downgradeText: {
    color: '#9CA3AF',
  },
  cardActions: {
    padding: 16,
    paddingTop: 8,
  },
  subscribeButton: {
    flex: 1,
  },
  currentPlanBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: '#E6F4F3',
    borderRadius: 8,
    flex: 1,
  },
  currentPlanText: {
    marginLeft: 8,
    color: '#0A3D38',
    fontWeight: '600',
  },
  downgradeInfo: {
    alignItems: 'center',
    paddingVertical: 12,
    backgroundColor: '#F3F4F6',
    borderRadius: 8,
    flex: 1,
  },
  downgradeInfoText: {
    marginTop: 4,
    color: '#6B7280',
    fontWeight: '500',
  },
  downgradeSubText: {
    marginTop: 2,
    color: '#9CA3AF',
    fontSize: 12,
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 48,
  },
  emptyText: {
    marginTop: 12,
    opacity: 0.6,
  },
  footer: {
    marginTop: 8,
    marginBottom: 24,
    padding: 12,
  },
  footerText: {
    textAlign: 'center',
    fontSize: 12,
    opacity: 0.5,
  },
});
