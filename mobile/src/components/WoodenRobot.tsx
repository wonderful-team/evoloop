// 3D 木头机器人组件 - 带表情动画

import React, { useRef, useEffect } from 'react';
import { View, StyleSheet, Animated } from 'react-native';

interface WoodenRobotProps {
  primaryColor?: string;
  mood?: 'neutral' | 'thinking' | 'speaking';
}

export function WoodenRobot({ primaryColor = '#109C8F', mood = 'neutral' }: WoodenRobotProps) {
  const floatAnim = useRef(new Animated.Value(0)).current;
  const blinkAnim = useRef(new Animated.Value(1)).current;
  const isBlinking = useRef(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    // 整体浮动动画
    Animated.loop(
      Animated.sequence([
        Animated.timing(floatAnim, {
          toValue: -8,
          duration: 2000,
          useNativeDriver: true,
        }),
        Animated.timing(floatAnim, {
          toValue: 0,
          duration: 2000,
          useNativeDriver: true,
        }),
      ])
    ).start();

    // 单次眨眼
    const doBlink = () => {
      if (isBlinking.current) return;
      isBlinking.current = true;
      
      Animated.sequence([
        Animated.timing(blinkAnim, {
          toValue: 0.1,
          duration: 80,
          useNativeDriver: true,
        }),
        Animated.timing(blinkAnim, {
          toValue: 1,
          duration: 100,
          useNativeDriver: true,
        }),
      ]).start((result?: { finished?: boolean }) => {
        isBlinking.current = false;
        // 鸿蒙原生驱动回调中的 result 可能为 undefined，必须做兼容防御
        if (!result || result.finished === false) {
          blinkAnim.setValue(1);
        }
      });
    };

    // 随机眨眼定时器
    const scheduleBlink = () => {
      const delay = 6000 + Math.random() * 8000;
      timerRef.current = setTimeout(() => {
        doBlink();
        scheduleBlink();
      }, delay);
    };
    
    scheduleBlink();
    
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      blinkAnim.stopAnimation();
      blinkAnim.setValue(1);
    };
  }, []);

  const renderExpression = () => {
    switch (mood) {
      case 'speaking':
        return (
          <>
            <View style={styles.eyesRow}>
              <EyeOpen primaryColor={primaryColor} />
              <EyeOpen primaryColor={primaryColor} />
            </View>
            <View style={styles.mouthSpeaking}>
              <View style={styles.mouthSpeakingInner} />
            </View>
          </>
        );
      default:
        return (
          <>
            <View style={styles.eyesRow}>
              <EyeWithBlink blinkAnim={blinkAnim} primaryColor={primaryColor} />
              <EyeWithBlink blinkAnim={blinkAnim} primaryColor={primaryColor} />
            </View>
            <View style={styles.mouthNeutral} />
          </>
        );
    }
  };



  return (
    <Animated.View
      style={[
        styles.robotContainer,
        { transform: [{ translateY: floatAnim }] },
      ]}
    >
      {/* 悬浮光环 */}
      <View style={[styles.robotGlow, { backgroundColor: primaryColor + '1A' }]} />
      
      {/* 机器人主体 */}
      <View style={styles.robotBody}>
        {/* 头部 */}
        <View style={styles.robotHead}>
          <View style={styles.woodTexture} />
          
          <View style={styles.antenna}>
            <View style={[styles.antennaBall, { backgroundColor: primaryColor }]} />
          </View>
          
          <View style={styles.screwTop}>
            <View style={styles.screwSlot} />
          </View>
          
          <View style={styles.faceContainer}>
            {renderExpression()}
          </View>
          
          <View style={[styles.sideScrew, { left: 6 }]} />
          <View style={[styles.sideScrew, { right: 6 }]} />
          
          <View style={[styles.cheek, { left: 6 }]} />
          <View style={[styles.cheek, { right: 6 }]} />
        </View>
        
        {/* 颈部 */}
        <View style={styles.robotNeck}>
          <View style={styles.neckRing} />
        </View>
        
        {/* 躯干+手臂 整体 */}
        <View style={styles.torsoWithArms}>
          {/* 左臂 */}
          <View style={[styles.arm, styles.armLeft]}>
            <View style={styles.armWood}>
              <View style={styles.armWoodGrain} />
            </View>
            <View style={styles.hand}>
              <View style={styles.finger} />
              <View style={styles.finger} />
              <View style={styles.finger} />
            </View>
          </View>

          {/* 躯干主体 */}
          <View style={styles.robotTorso}>
            <View style={styles.chestPanel}>
              <View style={[styles.coreLight, { backgroundColor: primaryColor }]} />
            </View>
            <View style={styles.torsoWoodGrain} />
          </View>

          {/* 右臂 */}
          <View style={[styles.arm, styles.armRight]}>
            <View style={styles.armWood}>
              <View style={styles.armWoodGrain} />
            </View>
            <View style={styles.hand}>
              <View style={styles.finger} />
              <View style={styles.finger} />
              <View style={styles.finger} />
            </View>
          </View>
        </View>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  robotContainer: {
    width: 160,
    height: 180,
    alignItems: 'center',
    justifyContent: 'center',
  },
  robotGlow: {
    position: 'absolute',
    width: 140,
    height: 140,
    borderRadius: 70,
    top: 10,
  },
  // 机器人主体
  robotBody: {
    alignItems: 'center',
  },
  // 头部
  robotHead: {
    width: 80,
    height: 70,
    backgroundColor: '#C4A574',
    borderRadius: 12,
    borderWidth: 3,
    borderColor: '#8B6914',
    borderBottomWidth: 4,
    borderRightWidth: 4,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.25,
    shadowRadius: 6,
    elevation: 6,
    zIndex: 10,
  },
  woodTexture: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.2,
    borderRadius: 9,
  },
  // 天线
  antenna: {
    position: 'absolute',
    top: -14,
    width: 4,
    height: 14,
    backgroundColor: '#8B7355',
    borderWidth: 1,
    borderColor: '#6B4423',
  },
  antennaBall: {
    position: 'absolute',
    top: -7,
    left: -4,
    width: 12,
    height: 12,
    borderRadius: 6,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.4,
    shadowRadius: 2,
  },
  // 螺丝
  screwTop: {
    position: 'absolute',
    top: 6,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#6B4423',
    alignItems: 'center',
    justifyContent: 'center',
  },
  screwSlot: {
    width: 5,
    height: 2,
    backgroundColor: '#3D2914',
  },
  sideScrew: {
    position: 'absolute',
    top: '50%',
    marginTop: -3,
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: '#6B4423',
  },
  // 脸部
  faceContainer: {
    alignItems: 'center',
    marginTop: 8,
  },
  cheek: {
    position: 'absolute',
    top: '58%',
    width: 8,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: '#D4A5A5',
    opacity: 0.5,
  },
  // 颈部
  robotNeck: {
    marginTop: -2,
    zIndex: 5,
  },
  neckRing: {
    width: 24,
    height: 6,
    backgroundColor: '#8B7355',
    borderRadius: 3,
    borderWidth: 1.5,
    borderColor: '#6B4423',
  },
  // 躯干+手臂 整体容器
  torsoWithArms: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'center',
    marginTop: -8,
    zIndex: 5,
  },
  // 躯干
  robotTorso: {
    width: 50,
    height: 42,
    backgroundColor: '#B8956A',
    borderRadius: 6,
    borderWidth: 2.5,
    borderColor: '#8B6914',
    borderBottomWidth: 3,
    borderRightWidth: 3,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 4,
    zIndex: 10,
  },
  chestPanel: {
    width: 34,
    height: 28,
    backgroundColor: '#A0826D',
    borderRadius: 4,
    borderWidth: 1.5,
    borderColor: '#6B4423',
    alignItems: 'center',
    justifyContent: 'center',
  },
  coreLight: {
    width: 14,
    height: 14,
    borderRadius: 7,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 6,
    elevation: 3,
  },
  torsoWoodGrain: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.2,
    borderRadius: 4,
  },
  // 手臂 - 向下张开欢迎姿势
  arm: {
    alignItems: 'center',
    marginTop: 2,
  },
  armLeft: {
    marginRight: -4,
    transform: [{ rotate: '50deg' }],
  },
  armRight: {
    marginLeft: -4,
    transform: [{ rotate: '-50deg' }],
  },
  armWood: {
    width: 14,
    height: 32,
    backgroundColor: '#B8956A',
    borderRadius: 7,
    borderWidth: 2,
    borderColor: '#8B6914',
    borderBottomWidth: 2.5,
    borderRightWidth: 2.5,
    position: 'relative',
    overflow: 'hidden',
  },
  armWoodGrain: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.15,
  },
  hand: {
    width: 16,
    height: 10,
    backgroundColor: '#A0826D',
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: '#6B4423',
    marginTop: -3,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 1,
  },
  finger: {
    width: 2.5,
    height: 4,
    backgroundColor: '#8B7355',
    borderRadius: 1,
    borderWidth: 0.5,
    borderColor: '#6B4423',
  },
  // 眼睛样式
  eyesRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 4,
    alignItems: 'center',
  },
  eyeContainer: {
    width: 22,
    height: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  eyeWhite: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.15,
    shadowRadius: 1,
    elevation: 1,
  },
  eyeWhiteLarge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.15,
    shadowRadius: 1,
    elevation: 1,
  },
  eyeBall: {
    width: 13,
    height: 13,
    borderRadius: 6.5,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  eyeBallLarge: {
    width: 16,
    height: 16,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  eyeShineMain: {
    position: 'absolute',
    top: 2,
    right: 2,
    width: 5,
    height: 5,
    borderRadius: 2.5,
    backgroundColor: '#FFFFFF',
    opacity: 0.9,
  },
  eyeShineSmall: {
    position: 'absolute',
    bottom: 2,
    left: 2,
    width: 2.5,
    height: 2.5,
    borderRadius: 1.25,
    backgroundColor: '#FFFFFF',
    opacity: 0.7,
  },
  eyeShineMainLarge: {
    position: 'absolute',
    top: 2,
    right: 3,
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#FFFFFF',
    opacity: 0.9,
  },
  eyeShineSmallLarge: {
    position: 'absolute',
    bottom: 2,
    left: 3,
    width: 3,
    height: 3,
    borderRadius: 1.5,
    backgroundColor: '#FFFFFF',
    opacity: 0.7,
  },

  // 嘴巴样式 - 默认轻微微笑
  mouthNeutral: {
    width: 16,
    height: 4,
    borderBottomWidth: 2,
    borderLeftWidth: 0.5,
    borderRightWidth: 0.5,
    borderTopWidth: 0,
    borderBottomLeftRadius: 4,
    borderBottomRightRadius: 4,
    borderColor: '#6B4423',
    marginTop: 3,
  },
  mouthSpeaking: {
    width: 16,
    height: 8,
    backgroundColor: '#6B4423',
    borderRadius: 4,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  mouthSpeakingInner: {
    width: 8,
    height: 3,
    backgroundColor: '#D4A5A5',
    borderRadius: 1.5,
  },
});

// 带眨眼的眼睛（置于 styles 后声明，确保鸿蒙 Hermes 引擎安全访问 styles）
function EyeWithBlink({ blinkAnim, primaryColor }: { blinkAnim: Animated.Value, primaryColor: string }) {
  return (
    <Animated.View 
      style={[
        styles.eyeContainer,
        { transform: [{ scaleY: blinkAnim }] }
      ]}
    >
      <View style={[styles.eyeWhite, { borderColor: primaryColor }]}>
        <View style={[styles.eyeBall, { backgroundColor: primaryColor }]}>
          <View style={styles.eyeShineMain} />
          <View style={styles.eyeShineSmall} />
        </View>
      </View>
    </Animated.View>
  );
}

function EyeOpen({ primaryColor }: { primaryColor: string }) {
  return (
    <View style={styles.eyeContainer}>
      <View style={[styles.eyeWhiteLarge, { borderColor: primaryColor }]}>
        <View style={[styles.eyeBallLarge, { backgroundColor: primaryColor }]}>
          <View style={styles.eyeShineMainLarge} />
          <View style={styles.eyeShineSmallLarge} />
        </View>
      </View>
    </View>
  );
}
