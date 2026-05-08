// 图形验证码组件

import React from 'react';
import { View, Image, TouchableOpacity, StyleSheet } from 'react-native';
import { Text } from 'react-native-paper';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { useTheme } from '@/theme';
import { useTranslation } from 'react-i18next';

interface CaptchaImageProps {
  captchaId?: string;
  captchaImage?: string;
  onRefresh: () => void;
  isLoading?: boolean;
}

export function CaptchaImage({
  captchaId,
  captchaImage,
  onRefresh,
  isLoading = false,
}: CaptchaImageProps) {
  const { colors } = useTheme();
  const { t } = useTranslation();

  return (
    <TouchableOpacity
      onPress={onRefresh}
      disabled={isLoading}
      style={styles.container}
    >
      {captchaImage ? (
        <Image
          source={{ uri: `data:image/png;base64,${captchaImage}` }}
          style={styles.image}
          resizeMode="cover"
        />
      ) : (
        <View style={[styles.placeholder, { backgroundColor: colors.surfaceVariant }]}>
          <MaterialIcons name="refresh" size={24} color={colors.text.secondary} />
          <Text variant="bodySmall" style={{ color: colors.text.secondary }}>
            {t('settings.account.refreshCaptcha')}
          </Text>
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    width: 100,
    height: 44,
    borderRadius: 8,
    overflow: 'hidden',
  },
  image: {
    width: '100%',
    height: '100%',
  },
  placeholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
    flexDirection: 'row',
    gap: 4,
  },
});
