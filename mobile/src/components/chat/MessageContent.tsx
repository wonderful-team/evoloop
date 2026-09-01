// 消息内容渲染组件 - 支持 Markdown、图片、文件、音频、代码高亮、表格、Mermaid 等

import React, { useState, useCallback, useMemo } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Image,
  Modal,
  Linking,
} from 'react-native';
import { Text, IconButton } from 'react-native-paper';
import Markdown from 'react-native-markdown-display';
import MaterialIcons from 'react-native-vector-icons/MaterialIcons';
import { WebView } from 'react-native-webview';
import { useTheme } from '@/theme';
import { useGlobalToast } from '@/contexts/ToastContext';
import { BASE_URL } from '@/constants/config';

import { useTranslation } from 'react-i18next';
import { CodeBlock } from './CodeBlock';

import { MarkdownTable } from './MarkdownTable';
import { AutoLinkPreview } from './LinkPreview';
import { MermaidChart, extractMermaidBlocks } from './MermaidChart';
import { EChartsChart } from './EChartsChart';
import { MapChart } from './MapChart';
import { extractAllSpecialBlocks } from './artifactUtils';

import Video from 'react-native-video';

// 图片查看器
interface ImageViewerProps {
  uri: string;
  visible: boolean;
  onClose: () => void;
}

export function ImageViewer({ uri, visible, onClose }: ImageViewerProps) {
  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <View style={styles.modalContainer}>
        <TouchableOpacity style={styles.modalOverlay} onPress={onClose}>
          <Image source={{ uri }} style={styles.fullImage} resizeMode="contain" />
        </TouchableOpacity>
        <IconButton
          icon="close"
          size={28}
          style={styles.closeButton}
          onPress={onClose}
        />
      </View>
    </Modal>
  );
}

// 图片消息组件
function ImageMessage({ url }: { url: string }) {
  const [viewerVisible, setViewerVisible] = useState(false);
  const imageUrl = url.startsWith('/api/') ? `${BASE_URL}${url}` : url;

  return (
    <>
      <TouchableOpacity
        style={styles.imageContainer}
        onPress={() => setViewerVisible(true)}
      >
        <Image source={{ uri: imageUrl }} style={styles.image} resizeMode="cover" />
      </TouchableOpacity>
      <ImageViewer
        uri={imageUrl}
        visible={viewerVisible}
        onClose={() => setViewerVisible(false)}
      />
    </>
  );
}

// 文件消息组件
function FileMessage({ url }: { url: string }) {
  const { t } = useTranslation();
  const { colors } = useTheme();
  const filename = decodeURIComponent(url.split('/').pop() || t('messageContent.fileFallback'));

  const ext = filename.split('.').pop()?.toLowerCase() || '';

  const getFileIcon = () => {
    const iconMap: Record<string, string> = {
      pdf: 'picture-as-pdf',
      doc: 'description',
      docx: 'description',
      xls: 'table-chart',
      xlsx: 'table-chart',
      txt: 'text-snippet',
      zip: 'folder-zip',
    };
    return iconMap[ext] || 'insert-drive-file';
  };

  const handlePress = useCallback(async () => {
    try {
      await Linking.openURL(url);
    } catch (error) {
      console.error('打开文件失败:', error);
    }
  }, [url]);

  return (
    <TouchableOpacity
      style={[styles.fileContainer, { backgroundColor: colors.surfaceVariant }]}
      onPress={handlePress}
    >
      <View style={[styles.fileIcon, { backgroundColor: colors.primaryContainer }]}>
        <MaterialIcons name={getFileIcon()} size={24} color={colors.primary} />
      </View>
      <View style={styles.fileInfo}>
        <Text numberOfLines={1} style={styles.fileName}>
          {filename}
        </Text>
        <Text style={[styles.fileHint, { color: colors.onSurfaceVariant }]}>
          {t('messageContent.clickToOpen')}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

// 音频消息组件
function AudioMessage({ url, name }: { url: string; name: string }) {
  const { colors } = useTheme();
  const [isPlaying, setIsPlaying] = useState(false);

  const togglePlay = useCallback(() => {
    setIsPlaying(prev => !prev);
  }, []);

  return (
    <TouchableOpacity
      style={[styles.audioContainer, { backgroundColor: colors.tertiaryContainer }]}
      onPress={togglePlay}
    >
      <Video
        source={{ uri: url }}
        paused={!isPlaying}
        onEnd={() => setIsPlaying(false)}
        style={{ width: 0, height: 0 }}
      />
      <View style={[styles.audioIcon, { backgroundColor: colors.tertiary }]}>
        <MaterialIcons
          name={isPlaying ? 'pause' : 'play-arrow'}
          size={20}
          color={colors.onTertiary}
        />
      </View>
      <Text numberOfLines={1} style={[styles.audioName, { color: colors.onTertiaryContainer }]}>
        {name}
      </Text>
    </TouchableOpacity>
  );
}

// 视频消息组件
function VideoMessage({ url, name }: { url: string; name: string }) {
  const { colors } = useTheme();
  const videoUrl = url.startsWith('/api/') ? `${BASE_URL}${url}` : url;

  return (
    <View style={styles.videoContainer}>
      <Text
        numberOfLines={1}
        style={[styles.videoName, { color: colors.onSurfaceVariant }]}
      >
        {name}
      </Text>
      <Video
        source={{ uri: videoUrl }}
        style={styles.video}
        controls
        resizeMode="contain"
      />
    </View>
  );
}

// 主内容组件
interface MessageContentProps {
  content: string;
  isUser?: boolean;
  isStreaming?: boolean;
}

export function MessageContent({ content, isUser = false, isStreaming = false }: MessageContentProps) {
  const { colors } = useTheme();
  const toast = useGlobalToast();
  const { t } = useTranslation();

  // 用 useMemo 缓存内容解析结果，避免每次渲染重复计算
  const parsedContent = useMemo(() => {
    if (typeof content !== 'string') {
      return { displayContent: '', parts: [] };
    }
    // 预处理：过滤内部标签
    let displayContent = content
      .replace(/<audit>[\s\S]*?(?:<\/audit>|$)/gi, '')
      .replace(/<thought>[\s\S]*?(?:<\/thought>|$)/gi, '')
      .replace(/<outcome>[\s\S]*?(?:<\/outcome>|$)/gi, '')
      .replace(/<reason>[\s\S]*?(?:<\/reason>|$)/gi, '')
      .trim();

    // 提取 report 内容
    const reportMatch = displayContent.match(/<report>([\s\S]*?)(?:<\/report>|$)/i);
    if (reportMatch) {
      displayContent = reportMatch[1].trim();
    }
    displayContent = displayContent.replace(/<\/?report>/gi, '');

    // 分割内容：按 [Image:/File:/Audio:/Video:] 分割
    const parts = displayContent.split(
      /(\[(?:Image|File|Audio|Video):\s*[^\]]+\]\([^)]+\)|\[(?:Image|File|Audio|Video):\s*[^\]]+\])/g
    );

    return { displayContent, parts };
  }, [content]);

  const { parts } = parsedContent;

  // 获取 Markdown 样式
  const markdownStyles = useMemo(() => getMarkdownTheme(isUser, colors), [isUser, colors]);

  // 定义 Markdown 渲染规则
  const markdownRules = useMemo(() => ({
    // 处理代码块
    // 处理代码块 (增强版：支持图表和地图分发)
    fence: (node: any) => {
      // 兼容性获取语言：优先尝试 sourceInfo，这是 markdown-display 常见的存放位置
      const language = (node.sourceInfo || node.attributes?.lang || 'text').toLowerCase();
      const content = node.content?.trim() || '';


      if (language === 'echarts') {
        try {
          const data = JSON.parse(content);
          return <EChartsChart key={node.key} data={data} />;
        } catch (e) {
          console.error('ECharts JSON 解析失败:', e);
        }
      }

      if (language === 'map') {
        try {
          const data = JSON.parse(content);
          return <MapChart key={node.key} data={data} />;
        } catch (e) {
          console.error('Map JSON 解析失败:', e);
        }
      }

      if (language === 'mermaid') {
        return <MermaidChart key={node.key} chart={content} />;
      }

      if (language === 'artifact' || language === 'html' || language === 'react') {
        const titleLabel = language === 'html' ? t('messageContent.htmlPreview') : language === 'react' ? t('messageContent.reactComponentPreview') : t('messageContent.artifactPreview');
        return (
          <View key={node.key} style={styles.artifactContainer}>
            <View style={styles.artifactTitleContainer}>
              <MaterialIcons name={language === 'react' ? "code" : "web"} size={16} color="#666" />
              <Text style={styles.artifactTitle}>{titleLabel}</Text>
            </View>
            <View style={[styles.artifactContent, { height: 250 }]}>
              <WebView
                source={{ html: content }}
                style={{ backgroundColor: 'transparent' }}
                scrollEnabled={true}
                originWhitelist={['*']}
              />
            </View>
          </View>
        );
      }

      return (
        <CodeBlock
          key={node.key}
          code={content}
          language={language}
        />
      );
    },
    code_block: (node: any) => (
      <CodeBlock
        key={node.key}
        code={node.content?.trim() || ''}
        language={node.attributes?.lang || 'text'}
      />
    ),

    // 禁用默认表格规则，我们目前使用手动解析和自定义组件
    table: () => null,

    // 处理标准 Markdown 链接中的 file:// 协议，拦截本地工作区路径并提示 Toast
    link: (node: any, children: any, parent: any, styles: any) => {
      const url = node.attributes?.href || '';
      if (url.startsWith('file://') || url.startsWith('/') || url.startsWith('./')) {
        return (
          <Text
            key={node.key}
            style={{ color: '#007acc', fontWeight: '500', textDecorationLine: 'underline' }}
            onPress={() => toast.warning(t('messageContent.localFilePreviewNotSupported'))}
          >
            {children}
          </Text>
        );
      }
      return (
        <Text
          key={node.key}
          style={styles.link}
          onPress={() => Linking.openURL(url).catch(err => console.error('打开链接失败:', err))}
        >
          {children}
        </Text>
      );
    },
  }), [toast, t]);

  if (typeof content !== 'string') {
    return (
      <Text style={{ color: colors.onSurface }}>
        {JSON.stringify(content, null, 2)}
      </Text>
    );
  }

  // 流式输出期间用纯文本渲染，避免每 token 重解析 Markdown
  if (isStreaming && !isUser) {
    return (
      <View style={styles.container}>
        <Text style={{ color: colors.onSurface, fontSize: 15, lineHeight: 22 }}>
          {parsedContent.displayContent}
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {parts.map((part, index) => {
        // 匹配图片
        const imageMatch = part.match(/^\[Image:\s*([^\]]+)\](?:\(([^)]+)\))?$/);
        if (imageMatch) {
          const url = imageMatch[2] || imageMatch[1];
          return <ImageMessage key={index} url={url} />;
        }

        // 匹配文件
        const fileMatch = part.match(/^\[File:\s*([^\]]+)\]$/);
        if (fileMatch) {
          return <FileMessage key={index} url={fileMatch[1]} />;
        }

        // 匹配音频
        const audioMatch = part.match(/^\[Audio:\s*([^\]]+)\](?:\(([^)]+)\))?$/);
        if (audioMatch) {
          const name = audioMatch[1];
          const url = audioMatch[2] || audioMatch[1];
          return <AudioMessage key={index} url={url} name={name} />;
        }

        // 匹配视频
        const videoMatch = part.match(/^\[Video:\s*([^\]]+)\](?:\(([^)]+)\))?$/);
        if (videoMatch) {
          const name = videoMatch[1];
          const url = videoMatch[2] || videoMatch[1];
          return <VideoMessage key={index} url={url} name={name} />;
        }

        // 使用统一拦截器提取所有特殊块 (Mermaid, ECharts, Map, Artifact)
        const allBlocks = extractAllSpecialBlocks(part);

        return (
          <View key={index}>
            {allBlocks.map((block, bIndex) => {
              if (block.type === 'mermaid') {
                return <MermaidChart key={bIndex} chart={block.content} />;
              }

              if (block.type === 'echarts') {
                try {
                  const data = JSON.parse(block.content);
                  return <EChartsChart key={bIndex} data={data} />;
                } catch (e) {
                  console.error('ECharts 解析失败:', e);
                }
              }

              if (block.type === 'map') {
                try {
                  const data = JSON.parse(block.content);
                  return <MapChart key={bIndex} data={data} />;
                } catch (e) {
                  console.error('Map 解析失败:', e);
                }
              }

              if (block.type === 'artifact' || block.type === 'html' || block.type === 'react') {
                const titleLabel = block.type === 'html' ? t('messageContent.htmlPreview') : block.type === 'react' ? t('messageContent.reactComponentPreview') : t('messageContent.artifactPreview');
                const artifactHtml = `
                  <!DOCTYPE html>
                  <html>
                    <head>
                      <meta charset="UTF-8">
                      <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
                      <style>
                        body { margin: 0; padding: 12px; font-family: -apple-system, system-ui; }
                        * { max-width: 100%; box-sizing: border-box; }
                      </style>
                    </head>
                    <body>
                      ${block.content}
                    </body>
                  </html>
                `;

                return (
                  <View key={bIndex} style={styles.artifactContainer}>
                    <View style={styles.artifactTitleContainer}>
                      <MaterialIcons name={block.type === 'react' ? "code" : "web"} size={16} color="#666" />
                      <Text style={styles.artifactTitle}>{titleLabel}</Text>
                    </View>
                    <View style={[styles.artifactContent, { height: 250 }]}>
                      <WebView
                        source={{ html: artifactHtml }}
                        style={{ backgroundColor: 'transparent' }}
                        scrollEnabled={true}
                        originWhitelist={['*']}
                      />
                    </View>
                  </View>
                );
              }


              // 文本部分处理：解析所有内嵌的表格与文本段落，避免截断
              const segments = extractTablesAndText(block.content);
              return (
                <View key={bIndex}>
                  {segments.map((seg, sIdx) => {
                    if (seg.type === 'table') {
                      const tableData = parseMarkdownTable(seg.content);
                      if (tableData && tableData.header.length > 0) {
                        return (
                          <MarkdownTable
                            key={sIdx}
                            header={tableData.header}
                            rows={tableData.rows}
                          />
                        );
                      }
                    }
                    return (
                      <View key={sIdx}>
                        <Markdown
                          style={markdownStyles}
                          rules={markdownRules}
                        >
                          {seg.content}
                        </Markdown>
                        <AutoLinkPreview text={seg.content} />
                      </View>
                    );
                  })}
                </View>
              );
            })}
          </View>
        );

      })}
    </View>
  );
}

// 获取 Markdown 主题样式
function getMarkdownTheme(isUser: boolean, colors: any) {
  const textColor = isUser ? colors.onPrimaryContainer : colors.onSurface;

  return {
    body: {
      color: textColor,
      fontSize: 16,
      lineHeight: 24,
    },


    // 标题样式
    heading1: {
      color: textColor,
      fontSize: 24,
      fontWeight: '700',
      marginTop: 16,
      marginBottom: 8,
      borderBottomWidth: 1,
      borderBottomColor: colors.outlineVariant,
      paddingBottom: 4,
    },
    heading2: {
      color: textColor,
      fontSize: 20,
      fontWeight: '700',
      marginTop: 14,
      marginBottom: 6,
    },
    heading3: {
      color: textColor,
      fontSize: 18,
      fontWeight: '600',
      marginTop: 12,
      marginBottom: 4,
    },
    heading4: {
      color: textColor,
      fontSize: 16,
      fontWeight: '600',
      marginTop: 10,
      marginBottom: 2,
    },
    paragraph: {
      marginVertical: 6, // 增加段落间距
    },
    code_inline: {
      backgroundColor: isUser ? 'rgba(0,0,0,0.1)' : colors.surfaceVariant,
      paddingHorizontal: 4,
      paddingVertical: 2,
      borderRadius: 4,
      fontFamily: 'monospace',
      fontSize: 13,
      color: isUser ? colors.onPrimaryContainer : colors.primary,
    },
    link: {
      color: colors.primary,
      textDecorationLine: 'underline',
    },
    // 列表样式
    list_item: {
      marginVertical: 3,
      flexDirection: 'row',
      alignItems: 'flex-start',
    },
    bullet_list: {
      marginVertical: 6,
    },
    ordered_list: {
      marginVertical: 6,
    },
    bullet_list_icon: {
      color: colors.primary,
      fontSize: 15,
      marginRight: 8,
      fontWeight: 'bold',
    },
    ordered_list_icon: {
      color: colors.primary,
      fontSize: 15,
      marginRight: 8,
      fontWeight: 'bold',
    },
    // 引用样式
    blockquote: {
      borderLeftWidth: 4,
      borderLeftColor: colors.primary + '80',
      backgroundColor: colors.surfaceVariant + '40',
      paddingLeft: 12,
      paddingVertical: 4,
      marginVertical: 8,
      borderRadius: 4,
    },
    // 分割线样式
    hr: {
      backgroundColor: colors.outlineVariant,
      height: 1,
      marginVertical: 16,
    },
    strong: {
      fontWeight: 'bold',
      color: isUser ? colors.onPrimaryContainer : colors.primary,
    },
    em: {
      fontStyle: 'italic',
    },
    // 基础表格样式（作为 fallback）
    table: {
      borderWidth: 1,
      borderColor: colors.outlineVariant,
      borderRadius: 4,
      marginVertical: 8,
    },
    th: {
      backgroundColor: colors.surfaceVariant,
      padding: 8,
    },
    td: {
      padding: 8,
      borderTopWidth: 1,
      borderTopColor: colors.outlineVariant,
    },
  };
}

// 解析 Markdown 表格
function parseMarkdownTable(text: string): { header: string[]; rows: string[][] } | null {
  const lines = text.trim().split('\n').filter(line => line.trim());

  // 找到表格行
  const tableLines: string[] = [];
  let inTable = false;

  for (const line of lines) {
    if (line.startsWith('|')) {
      tableLines.push(line);
      inTable = true;
    } else if (inTable) {
      break;
    }
  }

  if (tableLines.length < 2) return null;

  // 解析表头
  const header = tableLines[0]
    .split('|')
    .map(cell => cell.trim())
    .filter(cell => cell);

  if (header.length === 0) return null;

  // 跳过分隔符行，解析数据行
  const rows = tableLines.slice(2).map(line =>
    line
      .split('|')
      .map(cell => cell.trim())
      .filter((_, index, arr) => index > 0 && index < arr.length - 1)
  ).filter(row => row.length > 0);

  return { header, rows };
}

export interface ContentSegment {
  type: 'text' | 'table';
  content: string;
}

export function extractTablesAndText(text: string): ContentSegment[] {
  const lines = text.split('\n');
  const segments: ContentSegment[] = [];
  let currentTextLines: string[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimLine = line.trim();

    const isHeaderLine = trimLine.includes('|');
    const nextLine = lines[i + 1];
    const isDividerLine = nextLine && nextLine.trim().includes('|') && /^[|:\s-]+$/.test(nextLine.trim().replace(/[a-zA-Z0-9]/g, ''));

    if (isHeaderLine && isDividerLine) {
      if (currentTextLines.length > 0) {
        segments.push({ type: 'text', content: currentTextLines.join('\n') });
        currentTextLines = [];
      }

      const tableLines: string[] = [line, nextLine];
      i += 2;

      while (i < lines.length) {
        const rowLine = lines[i];
        if (rowLine.trim().includes('|')) {
          tableLines.push(rowLine);
          i++;
        } else {
          break;
        }
      }

      segments.push({ type: 'table', content: tableLines.join('\n') });
    } else {
      currentTextLines.push(line);
      i++;
    }
  }

  if (currentTextLines.length > 0) {
    segments.push({ type: 'text', content: currentTextLines.join('\n') });
  }

  return segments;
}

// 简化的链接预览组件
function LinkPreviewComponent({ url }: { url: string }) {
  const { colors } = useTheme();

  const handlePress = useCallback(async () => {
    try {
      await Linking.openURL(url);
    } catch (err) {
      console.error('无法打开链接:', err);
    }
  }, [url]);

  return (
    <TouchableOpacity
      style={[styles.linkPreview, { backgroundColor: colors.surfaceVariant }]}
      onPress={handlePress}
    >
      <MaterialIcons name="link" size={20} color={colors.primary} />
      <Text style={[styles.linkUrl, { color: colors.primary }]} numberOfLines={1}>
        {url}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  container: {
    // 移除 width: '100%'，让内容自适应宽度
  },
  imageContainer: {
    marginVertical: 4,
    borderRadius: 8,
    overflow: 'hidden',
    maxWidth: 250,
    maxHeight: 250,
  },
  image: {
    width: 250,
    height: 200,
  },
  fileContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 8,
    marginVertical: 4,
    maxWidth: 280,
  },
  fileIcon: {
    width: 40,
    height: 40,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  fileInfo: {
    marginLeft: 12,
    flex: 1,
  },
  fileName: {
    fontSize: 14,
    fontWeight: '500',
  },
  fileHint: {
    fontSize: 12,
    marginTop: 2,
  },
  audioContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    borderRadius: 20,
    marginVertical: 4,
    maxWidth: 250,
  },
  audioIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  audioName: {
    fontSize: 13,
    marginLeft: 8,
    flex: 1,
  },
  videoContainer: {
    marginVertical: 4,
    borderRadius: 8,
    overflow: 'hidden',
    maxWidth: 280,
  },
  videoName: {
    fontSize: 13,
    marginBottom: 4,
  },
  video: {
    width: 260,
    height: 160,
    borderRadius: 8,
    backgroundColor: '#000',
  },
  modalContainer: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  modalOverlay: {
    flex: 1,
    width: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },
  fullImage: {
    width: '90%',
    height: '70%',
  },
  closeButton: {
    position: 'absolute',
    top: 40,
    right: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.2)',
  },
  linkPreviewContainer: {
    marginTop: 8,
  },
  linkPreview: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 8,
    gap: 8,
  },
  linkUrl: {
    fontSize: 13,
    flex: 1,
  },
  artifactContainer: {
    marginVertical: 8,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#eee',
    overflow: 'hidden',
    backgroundColor: '#fff',
  },
  artifactTitleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    backgroundColor: '#f5f5f5',
    gap: 6,
  },
  artifactTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: '#666',
  },

  artifactContent: {
    padding: 12,
  },
});

