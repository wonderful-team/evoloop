// 个人中心页面 - 参考旧版设计，完善功能

import React, { useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Modal,
  Alert,
} from 'react-native';
import {
  Text,
  Button,
  List,
  Avatar,
  Divider,
  RadioButton,
  Portal,
  Dialog,
  ActivityIndicator,
} from 'react-native-paper';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/stores/authStore';
import { useTheme } from '@/theme';
import { router } from '@/utils/navigation';
import { maskMobile, formatDate } from '@/utils/format';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useSubscription } from '@/hooks/useSubscription';
import { useAuth } from '@/hooks/useAuth';
import { Linking } from 'react-native';
import ImagePicker from 'react-native-image-crop-picker';
import { authApi } from '@/services/api/auth';
import { useLoading } from '@/hooks/useLoading';
import { BASE_URL } from '@/constants/config';

// 自定义图标渲染组件 - 使用 MaterialIcons
function ListIcon({ icon, color }: { icon: string; color?: string }) {
  const { colors } = useTheme();
  return <MaterialIcons name={icon as any} size={24} color={color || colors.onSurfaceVariant} />;
}

// 语言选择器组件
function LanguageSelector({
  visible,
  onDismiss,
  currentLanguage,
  onSelect,
}: {
  visible: boolean;
  onDismiss: () => void;
  currentLanguage: string;
  onSelect: (lang: string) => void;
}) {
  const { t } = useTranslation();
  const { colors } = useTheme();

  const languages = [
    { code: 'zh', label: t('profile.chinese') },
    { code: 'en', label: t('profile.english') },
  ];

  return (
    <Portal>
      <Dialog visible={visible} onDismiss={onDismiss}>
        <Dialog.Title>{t('profile.selectLanguage')}</Dialog.Title>
        <Dialog.Content>
          {languages.map((lang) => (
            <TouchableOpacity
              key={lang.code}
              style={styles.languageItem}
              onPress={() => {
                onSelect(lang.code);
                onDismiss();
              }}
            >
              <Text style={{ flex: 1 }}>{lang.label}</Text>
              <RadioButton
                value={lang.code}
                status={currentLanguage?.startsWith(lang.code) ? 'checked' : 'unchecked'}
              />
            </TouchableOpacity>
          ))}
        </Dialog.Content>
        <Dialog.Actions>
          <Button onPress={onDismiss}>{t('common.cancel')}</Button>
        </Dialog.Actions>
      </Dialog>
    </Portal>
  );
}

// 统计卡片组件
function StatCard({
  label,
  value,
  icon,
  colors,
}: {
  label: string;
  value: string;
  icon: string;
  colors: any;
}) {
  return (
    <View style={[styles.statCard, { backgroundColor: colors.surfaceVariant }]}>
      <MaterialIcons name={icon} size={24} color={colors.primary} />
      <Text variant="titleLarge" style={[styles.statValue, { color: colors.onSurface }]}>
        {value}
      </Text>
      <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant }}>
        {label}
      </Text>
    </View>
  );
}

// 会员卡片组件
function MembershipCard({
  userInfo,
  isMember,
  onPress,
  colors,
}: {
  userInfo: any;
  isMember: boolean;
  onPress: () => void;
  colors: any;
}) {
  const { t } = useTranslation();

  const expireDate = userInfo?.memberExpireTime
    ? formatDate(userInfo.memberExpireTime * 1000)
    : '';

  return (
    <TouchableOpacity
      activeOpacity={0.9}
      onPress={onPress}
      style={styles.membershipCard}
    >
      {/* 渐变背景层 - 会员金色渐变 / 非会员 teal 深灰渐变 */}
      <View
        style={[
          styles.membershipGradient,
          {
            backgroundColor: isMember ? '#D97706' : '#374151',
          },
        ]}
      />
      <View
        style={[
          styles.membershipGradientOverlay,
          {
            backgroundColor: isMember
              ? 'rgba(251, 191, 36, 0.4)'
              : 'rgba(107, 114, 128, 0.3)',
          },
        ]}
      />

      {/* 装饰圆圈 */}
      <View style={styles.decorCircle1} />
      <View style={styles.decorCircle2} />

      <View style={styles.membershipContent}>
        <View style={styles.membershipHeader}>
          <View>
            <Text style={styles.membershipLabel}>{t('profile.currentPlan')}</Text>
            <View style={styles.membershipTitleRow}>
              <MaterialIcons
                name={isMember ? 'card-membership' : 'credit-card'}
                size={24}
                color="#FFF"
              />
              <Text style={styles.membershipTitle}>
                {userInfo?.memberLevelName || t('profile.freePlan')}
              </Text>
            </View>
          </View>
          {isMember && (
            <View style={styles.proBadge}>
              <Text style={styles.proBadgeText}>PRO</Text>
            </View>
          )}
        </View>

        <View style={styles.membershipInfo}>
          {isMember ? (
            <>
              <Text style={styles.membershipText}>
                {t('profile.validUntil')} {expireDate}
              </Text>
              <Text style={[styles.membershipText, { opacity: 0.75 }]}>
                {t('profile.autoRenewalOff')}
              </Text>
            </>
          ) : (
            <Text style={styles.membershipText}>{t('profile.upgradeHint')}</Text>
          )}
        </View>

        <View style={styles.membershipFooter}>
          <View style={[styles.manageButton, { backgroundColor: colors.surface }]}>
            <Text style={[styles.manageButtonText, { color: colors.onSurface }]}>
              {isMember ? t('profile.manageSubscription') : t('profile.upgradeNow')}
            </Text>
            <MaterialIcons name="chevron-right" size={16} color={colors.onSurface} />
          </View>
        </View>
      </View>
    </TouchableOpacity>
  );
}

// 游客模式下的个人中心
function GuestProfile() {
  const { t, i18n } = useTranslation();
  const { colors } = useTheme();
  const [showLanguageSelector, setShowLanguageSelector] = useState(false);

  const handleLanguageChange = useCallback((lang: string) => {
    i18n.changeLanguage(lang);
  }, [i18n]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* 头部 */}
        <View style={styles.guestHeader}>
          <View style={[styles.guestAvatar, { backgroundColor: colors.surfaceVariant }]}>
            <MaterialIcons name="person-outline" size={48} color={colors.onSurfaceVariant} />
          </View>
          <Text variant="headlineSmall" style={[styles.guestTitle, { color: colors.onSurface }]}>
            {t('profile.guestTitle')}
          </Text>
          <Text variant="bodyMedium" style={{ color: colors.onSurfaceVariant }}>
            {t('profile.guestDesc')}
          </Text>

          <View style={styles.guestButtons}>
            <Button
              mode="contained"
              style={styles.loginButton}
              onPress={() => router.push('Auth')}
            >
              {t('auth.login.submit')}
            </Button>
            <Button
              mode="outlined"
              style={styles.registerButton}
              onPress={() => router.push('Register')}
            >
              {t('auth.login.signUp')}
            </Button>
          </View>
        </View>

        <Divider style={styles.divider} />

        {/* 功能列表 */}
        <List.Section>
          <List.Item
            title={t('profile.language')}
            left={() => <ListIcon icon="translate" />}
            right={() => (
              <View style={styles.listValue}>
                <Text style={{ color: colors.onSurfaceVariant }}>
                  {i18n.language?.startsWith('zh') ? t('profile.chinese') : t('profile.english')}
                </Text>
                <MaterialIcons name="chevron-right" size={20} color={colors.onSurfaceVariant} />
              </View>
            )}
            onPress={() => setShowLanguageSelector(true)}
          />
          <List.Item
            title={t('profile.manual')}
            left={() => <ListIcon icon="help-outline" />}
            right={() => <ListIcon icon="chevron-right" />}
            onPress={() => router.push('Help')}
          />
        </List.Section>
      </ScrollView>

      <LanguageSelector
        visible={showLanguageSelector}
        onDismiss={() => setShowLanguageSelector(false)}
        currentLanguage={i18n.language}
        onSelect={handleLanguageChange}
      />
    </SafeAreaView>
  );
}

// 登录用户的个人中心
function UserProfile() {
  const { t, i18n } = useTranslation();
  const { colors } = useTheme();
  const { userInfo, logout } = useAuthStore();
  const { hasActiveSubscription, currentLevelName, remainingDays, isLoading } = useSubscription();
  const { deleteAccount } = useAuth();
  const [showLanguageSelector, setShowLanguageSelector] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [avatarError, setAvatarError] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  const { execute: executeUpload } = useLoading();

  const handleLogout = useCallback(() => {
    Alert.alert(
      t('profile.logout'),
      t('profile.logoutConfirm'),
      [
        { text: t('common.cancel'), style: 'cancel' },
        {
          text: t('profile.logout'),
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('Auth');
          },
        },
      ]
    );
  }, [logout, t]);

  const handleLanguageChange = useCallback((lang: string) => {
    i18n.changeLanguage(lang);
  }, [i18n]);

  const goToSubscription = useCallback(() => {
    router.push('Plans');
  }, []);

  const goToSettings = useCallback(() => {
    router.push('Settings');
  }, []);

  const handleDeleteAccount = useCallback(async () => {
    setShowDeleteConfirm(false);
    try {
      await deleteAccount();
      Alert.alert(t('common.success'), t('profile.deleteAccountSuccess'));
    } catch (error: any) {
      Alert.alert(t('common.error.title') || '错误', error.message || t('profile.deleteAccountFailed'));
    }
  }, [deleteAccount, t]);

  const openMemberCenter = useCallback(async () => {
    await Linking.openURL(`${BASE_URL}/member`);
  }, []);

  // 头像上传
  const handleAvatarPress = useCallback(() => {
    Alert.alert(
      t('profile.changeAvatar') || '更换头像',
      '',
      [
        { text: t('common.cancel') || '取消', style: 'cancel' },
        {
          text: t('profile.takePhoto') || '拍照',
          onPress: () => pickAndUploadAvatar('camera'),
        },
        {
          text: t('profile.chooseFromAlbum') || '从相册选择',
          onPress: () => pickAndUploadAvatar('gallery'),
        },
      ]
    );
  }, [t]);

  const pickAndUploadAvatar = useCallback(async (source: 'camera' | 'gallery') => {
    try {
      setUploadingAvatar(true);

      const image = source === 'camera'
        ? await ImagePicker.openCamera({
            width: 300,
            height: 300,
            cropping: true,
            cropperCircleOverlay: true,
            includeBase64: true,
            compressImageMaxWidth: 300,
            compressImageMaxHeight: 300,
            compressImageQuality: 0.8,
          })
        : await ImagePicker.openPicker({
            width: 300,
            height: 300,
            cropping: true,
            cropperCircleOverlay: true,
            includeBase64: true,
            compressImageMaxWidth: 300,
            compressImageMaxHeight: 300,
            compressImageQuality: 0.8,
          });

      if (!image.data) {
        throw new Error(t('profile.avatarImageError') || '无法获取图片数据');
      }

      // base64 数据可能需要加上前缀
      const base64Data = image.data.startsWith('data:')
        ? image.data
        : `data:${image.mime || 'image/jpeg'};base64,${image.data}`;

      // 1. 上传头像到服务器
      const uploadRes = await executeUpload(authApi.uploadHeadimgBase64(base64Data));
      const picPath = uploadRes.pic_path;

      // 2. 修改用户头像
      await executeUpload(authApi.modifyHeadimg(picPath));

      // 3. 更新本地状态
      const { updateUserInfo } = useAuthStore.getState();
      updateUserInfo({ avatar: picPath });

      Alert.alert(t('common.success') || '成功', t('profile.avatarUpdated') || '头像已更新');
    } catch (error: any) {
      console.error('Avatar upload error:', error);
      // 用户取消不提示错误
      if (error.code !== 'E_PICKER_CANCELLED' && error.code !== 'E_USER_CANCELLED') {
        Alert.alert(
          t('common.error.title') || '错误',
          error.message || t('profile.avatarUpdateFailed') || '头像更新失败，请重试'
        );
      }
    } finally {
      setUploadingAvatar(false);
    }
  }, [t, executeUpload]);

  const balance = userInfo?.balance || '0.00';
  const points = userInfo?.point || 0;

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* 用户信息头部 - 左右排列 */}
        <View style={styles.userHeader}>
          <TouchableOpacity
            onPress={handleAvatarPress}
            disabled={uploadingAvatar}
            activeOpacity={0.8}
            style={styles.avatarWrapper}
          >
            {uploadingAvatar ? (
              <View style={[styles.avatarFallback, { backgroundColor: colors.surfaceVariant }]}>
                <ActivityIndicator size="small" color={colors.primary} />
              </View>
            ) : userInfo?.avatar && !avatarError ? (
              <Avatar.Image
                size={64}
                source={{ uri: userInfo.avatar }}
                style={styles.avatar}
                onError={() => setAvatarError(true)}
              />
            ) : (
              <View style={[styles.avatarFallback, { backgroundColor: colors.surfaceVariant }]}>
                <MaterialIcons name="person" size={32} color={colors.onSurfaceVariant} />
              </View>
            )}
            {/* 编辑图标 */}
            <View style={[styles.avatarEditBadge, { backgroundColor: colors.primary }]}>
              <MaterialIcons name="camera-alt" size={12} color="#FFF" />
            </View>
          </TouchableOpacity>
          <View style={styles.userInfo}>
            <Text variant="titleLarge" style={[styles.name, { color: colors.onSurface }]}>
              {userInfo?.nickname || t('profile.user')}
            </Text>
            <Text variant="bodyMedium" style={{ color: colors.onSurfaceVariant }}>
              {maskMobile(userInfo?.mobile || '')}
            </Text>
            {userInfo?.email && (
              <Text variant="bodySmall" style={{ color: colors.onSurfaceVariant, marginTop: 2 }}>
                {userInfo.email}
              </Text>
            )}
          </View>
        </View>

        {/* 会员卡片 */}
        <MembershipCard
          userInfo={userInfo}
          isMember={hasActiveSubscription}
          onPress={goToSubscription}
          colors={colors}
        />

        {/* 余额和积分 */}
        <View style={styles.statsRow}>
          <StatCard
            label={t('profile.balance')}
            value={`¥${balance}`}
            icon="account-balance-wallet"
            colors={colors}
          />
          <StatCard
            label={t('profile.points')}
            value={points.toString()}
            icon="stars"
            colors={colors}
          />
        </View>

        <Divider style={styles.divider} />

        {/* 功能列表 */}
        <List.Section>
          <List.Item
            title={t('profile.settings')}
            left={() => <ListIcon icon="settings" />}
            right={() => <ListIcon icon="chevron-right" />}
            onPress={goToSettings}
          />
          <List.Item
            title={t('profile.manageSubscription')}
            left={() => <ListIcon icon="card-membership" />}
            right={() => <ListIcon icon="chevron-right" />}
            onPress={goToSubscription}
          />
          <List.Item
            title={t('profile.memberCenter')}
            left={() => <ListIcon icon="open-in-new" />}
            right={() => <ListIcon icon="open-in-new" />}
            onPress={openMemberCenter}
          />
        </List.Section>

        <Divider style={styles.divider} />

        <List.Section>
          <List.Item
            title={t('profile.language')}
            left={() => <ListIcon icon="translate" />}
            right={() => (
              <View style={styles.listValue}>
                <Text style={{ color: colors.onSurfaceVariant }}>
                  {i18n.language?.startsWith('zh') ? t('profile.chinese') : t('profile.english')}
                </Text>
                <MaterialIcons name="chevron-right" size={20} color={colors.onSurfaceVariant} />
              </View>
            )}
            onPress={() => setShowLanguageSelector(true)}
          />
          <List.Item
            title={t('profile.manual')}
            left={() => <ListIcon icon="help-outline" />}
            right={() => <ListIcon icon="chevron-right" />}
            onPress={() => router.push('Help')}
          />
        </List.Section>

        <Divider style={styles.divider} />

        <List.Section>
          <List.Item
            title={t('profile.deleteAccount')}
            titleStyle={{ color: colors.error }}
            left={() => <ListIcon icon="delete-forever" color={colors.error} />}
            right={() => <ListIcon icon="chevron-right" color={colors.error} />}
            onPress={() => setShowDeleteConfirm(true)}
          />
        </List.Section>

        {/* 退出登录按钮 */}
        <View style={styles.footer}>
          <Button
            mode="outlined"
            onPress={handleLogout}
            style={[styles.logoutButton, { borderColor: colors.error }]}
            textColor={colors.error}
            icon="logout"
          >
            {t('profile.logout')}
          </Button>
        </View>
      </ScrollView>

      {/* 语言选择器 */}
      <LanguageSelector
        visible={showLanguageSelector}
        onDismiss={() => setShowLanguageSelector(false)}
        currentLanguage={i18n.language}
        onSelect={handleLanguageChange}
      />

      {/* 注销账号确认 */}
      <Portal>
        <Dialog visible={showDeleteConfirm} onDismiss={() => setShowDeleteConfirm(false)}>
          <Dialog.Title>{t('profile.confirmDelete')}</Dialog.Title>
          <Dialog.Content>
            <Text>{t('profile.deleteAccountWarning')}</Text>
          </Dialog.Content>
          <Dialog.Actions>
            <Button onPress={() => setShowDeleteConfirm(false)}>{t('common.cancel')}</Button>
            <Button onPress={handleDeleteAccount} textColor={colors.error}>
              {t('profile.confirm')}
            </Button>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </SafeAreaView>
  );
}

export default function ProfileScreen() {
  const { isLoggedIn } = useAuthStore();

  if (!isLoggedIn) {
    return <GuestProfile />;
  }

  return <UserProfile />;
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
  },
  // 游客模式样式
  guestHeader: {
    alignItems: 'center',
    paddingVertical: 32,
  },
  guestAvatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  guestTitle: {
    fontWeight: '600',
    marginBottom: 8,
  },
  guestButtons: {
    width: '100%',
    maxWidth: 280,
    marginTop: 24,
    gap: 12,
  },
  loginButton: {
    borderRadius: 8,
  },
  registerButton: {
    borderRadius: 8,
  },
  // 用户模式样式
  userHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 16,
    gap: 16,
  },
  avatar: {
    // Avatar.Image 自带尺寸
  },
  avatarWrapper: {
    position: 'relative',
  },
  avatarFallback: {
    width: 64,
    height: 64,
    borderRadius: 32,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarEditBadge: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 22,
    height: 22,
    borderRadius: 11,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#FFFFFF',
  },
  userInfo: {
    flex: 1,
    justifyContent: 'center',
  },
  name: {
    fontWeight: '600',
    marginBottom: 2,
  },
  // 会员卡片样式
  membershipCard: {
    borderRadius: 16,
    marginVertical: 16,
    overflow: 'hidden',
    position: 'relative',
  },
  membershipGradient: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  membershipGradientOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
  },
  decorCircle1: {
    position: 'absolute',
    top: -40,
    right: -40,
    width: 120,
    height: 120,
    borderRadius: 60,
    backgroundColor: 'rgba(255,255,255,0.15)',
  },
  decorCircle2: {
    position: 'absolute',
    bottom: -20,
    left: -20,
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: 'rgba(0,0,0,0.08)',
  },
  membershipContent: {
    padding: 20,
    position: 'relative',
    zIndex: 1,
  },
  membershipHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 16,
  },
  membershipLabel: {
    color: 'rgba(255,255,255,0.8)',
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 4,
  },
  membershipTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  membershipTitle: {
    color: '#FFF',
    fontSize: 22,
    fontWeight: 'bold',
  },
  proBadge: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  proBadgeText: {
    color: '#FFF',
    fontSize: 10,
    fontWeight: '600',
  },
  membershipInfo: {
    marginBottom: 16,
  },
  membershipText: {
    color: '#FFF',
    fontSize: 13,
  },
  membershipFooter: {
    borderTopWidth: 1,
    borderTopColor: 'rgba(255,255,255,0.2)',
    paddingTop: 12,
    alignItems: 'flex-end',
  },
  manageButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.9)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    gap: 4,
  },
  manageButtonText: {
    fontSize: 12,
    fontWeight: '600',
  },
  // 统计卡片
  statsRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 8,
  },
  statCard: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  statValue: {
    fontWeight: 'bold',
    marginVertical: 8,
  },
  // 通用样式
  divider: {
    marginVertical: 8,
  },
  listValue: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  languageItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
  },
  footer: {
    paddingVertical: 16,
    marginTop: 8,
  },
  logoutButton: {
    borderRadius: 8,
  },
});
