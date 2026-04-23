import React from 'react';
import { Image, StyleSheet, TouchableOpacity, View } from 'react-native';
import { router } from '@/utils/navigation';

interface LogoProps {
  variant?: 'icon' | 'full';
  size?: number;
  asLink?: boolean;
  style?: object;
}

export function Logo({
  variant = 'icon',
  size = 64,
  asLink = true,
  style,
}: LogoProps) {
  const logoSource =
    variant === 'icon'
      ? require('@/assets/images/icon.png')
      : require('@/assets/images/icon.png');

  const content = (
    <Image
      source={logoSource}
      style={[
        styles.image,
        { width: size, height: size, borderRadius: size / 4 },
        style,
      ]}
      resizeMode="contain"
    />
  );

  if (asLink) {
    return (
      <TouchableOpacity
        activeOpacity={0.8}
        onPress={() => router.replace('Main')}
      >
        {content}
      </TouchableOpacity>
    );
  }

  return <View>{content}</View>;
}

const styles = StyleSheet.create({
  image: {
    backgroundColor: 'transparent',
  },
});
