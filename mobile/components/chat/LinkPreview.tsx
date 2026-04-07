// 链接预览组件 - 显示 URL 卡片

import React, { useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Linking,
  Image,
  ActivityIndicator,
} from 'react-native';
import { Text } from 'react-native-paper';
import { useTheme } from '@/theme';
import { MaterialIcons } from '@expo/vector-icons';

interface LinkPreviewData {
  url: string;
  title?: string;
  description?: string;
  image?: string;
  siteName?: string;
}

interface LinkPreviewProps {
  url: string;
}

// 模拟获取链接预览数据
// 实际项目中可以使用 @flyerhq/react-native-link-preview 或后端 API
const fetchLinkPreview = async (url: string): Promise<LinkPreviewData | null> => {
  // 这里模拟一些常见网站的预览
  const mockData: Record<string, Partial<LinkPreviewData>> = {
    'github.com': {
      title: 'GitHub',
      description: 'Where the world builds software',
      siteName: 'GitHub',
    },
    'stackoverflow.com': {
      title: 'Stack Overflow',
      description: 'Where developers learn, share, and build careers',
      siteName: 'Stack Overflow',
    },
    'youtube.com': {
      title: 'YouTube',
      description: 'Share your videos with friends, family, and the world',
      siteName: 'YouTube',
    },
    'docs.expo.dev': {
      title: 'Expo Documentation',
      description: 'Learn how to build native apps with Expo',
      siteName: 'Expo',
    },
    'reactnative.dev': {
      title: 'React Native',
      description: 'A framework for building native apps using React',
      siteName: 'React Native',
    },
  };

  // 模拟延迟
  await new Promise(resolve => setTimeout(resolve, 500));

  // 查找匹配的域名
  const domain = Object.keys(mockData).find(d => url.includes(d));
  if (domain) {
    return {
      url,
      ...mockData[domain],
    } as LinkPreviewData;
  }

  // 如果没有匹配的，返回基础数据
  try {
    const urlObj = new URL(url);
    return {
      url,
      title: urlObj.hostname,
      siteName: urlObj.hostname,
    };
  } catch {
    return { url };
  }
};

export function LinkPreview({ url }: LinkPreviewProps) {
  const { colors } = useTheme();
  const [previewData, setPreviewData] = useState<LinkPreviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [imageError, setImageError] = useState(false);

  // 获取预览数据
  React.useEffect(() => {
    let mounted = true;
    fetchLinkPreview(url)
      .then(data => {
        if (mounted) {
          setPreviewData(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (mounted) {
          setError(true);
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, [url]);

  const handlePress = useCallback(async () => {
    try {
      await Linking.openURL(url);
    } catch (err) {
      console.error('无法打开链接:', err);
    }
  }, [url]);

  if (loading) {
    return (
      <View style={[styles.container, { backgroundColor: colors.surfaceVariant }]}>
        <ActivityIndicator size="small" color={colors.primary} />
      </View>
    );
  }

  if (error || !previewData) {
    return (
      <TouchableOpacity
        style={[styles.container, { backgroundColor: colors.surfaceVariant }]}
        onPress={handlePress}
      >
        <View style={styles.errorContent}>
          <MaterialIcons name="link" size={24} color={colors.outline} />
          <Text style={[styles.errorText, { color: colors.onSurfaceVariant }]}>
            {url}
          </Text>
        </View>
      </TouchableOpacity>
    );
  }

  return (
    <TouchableOpacity
      style={[styles.container, { backgroundColor: colors.surfaceVariant }]}
      onPress={handlePress}
      activeOpacity={0.8}
    >
      {previewData.image && !imageError && (
        <Image
          source={{ uri: previewData.image }}
          style={styles.image}
          resizeMode="cover"
          onError={() => setImageError(true)}
        />
      )}
      
      <View style={styles.content}>
        {previewData.siteName && (
          <Text style={[styles.siteName, { color: colors.outline }]}>
            {previewData.siteName}
          </Text>
        )}
        
        {previewData.title && (
          <Text 
            style={[styles.title, { color: colors.onSurface }]}
            numberOfLines={2}
          >
            {previewData.title}
          </Text>
        )}
        
        {previewData.description && (
          <Text 
            style={[styles.description, { color: colors.onSurfaceVariant }]}
            numberOfLines={2}
          >
            {previewData.description}
          </Text>
        )}
        
        <Text 
          style={[styles.url, { color: colors.primary }]}
          numberOfLines={1}
        >
          {url}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

// 在文本中自动检测并渲染链接预览
interface AutoLinkPreviewProps {
  text: string;
}

export function AutoLinkPreview({ text }: AutoLinkPreviewProps) {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const urls = text.match(urlRegex);
  
  // 只显示第一个链接的预览
  const firstUrl = urls?.[0];
  
  if (!firstUrl) return null;
  
  return <LinkPreview url={firstUrl} />;
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 12,
    overflow: 'hidden',
    marginVertical: 8,
  },
  image: {
    width: '100%',
    height: 120,
    backgroundColor: '#f0f0f0',
  },
  content: {
    padding: 12,
  },
  siteName: {
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  title: {
    fontSize: 14,
    fontWeight: '600',
    lineHeight: 20,
    marginBottom: 4,
  },
  description: {
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 8,
  },
  url: {
    fontSize: 12,
  },
  errorContent: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    gap: 8,
  },
  errorText: {
    fontSize: 12,
    flex: 1,
  },
});
