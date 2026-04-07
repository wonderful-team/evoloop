// 新手引导页面

import React, { useState, useRef } from 'react';
import {
  View,
  StyleSheet,
  Dimensions,
  FlatList,
  TouchableOpacity,
} from 'react-native';
import { Text, Button } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { useTheme } from '@/components/ui/ThemeProvider';
import { useTranslation } from 'react-i18next';
import { storage } from '@/services/storage/mmkv';

const { width } = Dimensions.get('window');

interface OnboardingSlide {
  id: string;
  title: string;
  subtitle: string;
  icon: string;
}

export default function OnboardingScreen() {
  const router = useRouter();
  const { colors } = useTheme();
  const { t } = useTranslation();
  const [currentIndex, setCurrentIndex] = useState(0);
  const flatListRef = useRef<FlatList>(null);

  const slides: OnboardingSlide[] = [
    {
      id: '1',
      title: 'EvoLoop AI',
      subtitle: '您的随身通用智能体。\n无论是跨平台编排、编写代码，\n还是解答疑惑，在这里随时开始。',
      icon: '🤖',
    },
    {
      id: '2',
      title: '双重世界',
      subtitle: 'EvoLoop 拥有两面。\n左右滑动试试看？\n在云端智能与设备管理间无缝切换。',
      icon: '🌐',
    },
    {
      id: '3',
      title: '连接您的工作站',
      subtitle: '在电脑安装客户端，解锁远程控制能力。\n远程执行命令、管理文件，尽在掌握。',
      icon: '💻',
    },
    {
      id: '4',
      title: '语音助手',
      subtitle: '点击麦克风图标，开始语音对话。\n支持自然语言控制设备和获取答案。',
      icon: '🎤',
    },
    {
      id: '5',
      title: '高效技巧',
      subtitle: '点击输入框旁的图标，体验更多能力。\n现在，开始您的 EvoLoop 之旅吧！',
      icon: '✨',
    },
  ];

  const handleNext = () => {
    if (currentIndex < slides.length - 1) {
      flatListRef.current?.scrollToIndex({
        index: currentIndex + 1,
        animated: true,
      });
    } else {
      completeOnboarding();
    }
  };

  const handleSkip = () => {
    completeOnboarding();
  };

  const completeOnboarding = () => {
    storage.set('has_completed_onboarding', true);
    router.replace('/(main)');
  };

  const renderSlide = ({ item }: { item: OnboardingSlide }) => (
    <View style={[styles.slide, { width }]}>
      <View style={styles.iconContainer}>
        <Text style={styles.icon}>{item.icon}</Text>
      </View>
      <Text
        variant="headlineMedium"
        style={[styles.title, { color: colors.colors.primary }]}
      >
        {item.title}
      </Text>
      <Text
        variant="bodyLarge"
        style={[styles.subtitle, { color: colors.colors.onSurfaceVariant }]}
      >
        {item.subtitle}
      </Text>
    </View>
  );

  const renderDots = () => (
    <View style={styles.dotsContainer}>
      {slides.map((_, index) => (
        <View
          key={index}
          style={[
            styles.dot,
            {
              backgroundColor:
                index === currentIndex
                  ? colors.colors.primary
                  : colors.colors.surfaceVariant,
              width: index === currentIndex ? 24 : 8,
            },
          ]}
        />
      ))}
    </View>
  );

  return (
    <View style={[styles.container, { backgroundColor: colors.colors.background }]}>
      {/* 跳过按钮 */}
      <TouchableOpacity style={styles.skipButton} onPress={handleSkip}>
        <Text variant="bodyMedium" style={{ color: colors.colors.onSurfaceVariant }}>
          跳过
        </Text>
      </TouchableOpacity>

      {/* 幻灯片 */}
      <FlatList
        ref={flatListRef}
        data={slides}
        renderItem={renderSlide}
        keyExtractor={(item) => item.id}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        onMomentumScrollEnd={(event) => {
          const index = Math.round(event.nativeEvent.contentOffset.x / width);
          setCurrentIndex(index);
        }}
        scrollEnabled={true}
      />

      {/* 底部控制 */}
      <View style={styles.footer}>
        {renderDots()}

        <View style={styles.buttonContainer}>
          <Button
            mode="contained"
            onPress={handleNext}
            style={styles.button}
            contentStyle={styles.buttonContent}
          >
            {currentIndex === slides.length - 1 ? '开始体验' : '下一步'}
          </Button>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  skipButton: {
    position: 'absolute',
    top: 60,
    right: 24,
    zIndex: 10,
  },
  slide: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 40,
  },
  iconContainer: {
    marginBottom: 40,
  },
  icon: {
    fontSize: 80,
  },
  title: {
    marginBottom: 20,
    fontWeight: 'bold',
    textAlign: 'center',
  },
  subtitle: {
    textAlign: 'center',
    lineHeight: 24,
  },
  footer: {
    paddingHorizontal: 24,
    paddingBottom: 40,
  },
  dotsContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 32,
    gap: 8,
  },
  dot: {
    height: 8,
    borderRadius: 4,
  },
  buttonContainer: {
    paddingHorizontal: 16,
  },
  button: {
    borderRadius: 28,
  },
  buttonContent: {
    height: 56,
  },
});
