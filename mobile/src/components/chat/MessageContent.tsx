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
import { useTheme } from '@/theme';
import { CodeBlock } from './CodeBlock';
import { MarkdownTable } from './MarkdownTable';
import { AutoLinkPreview } from './LinkPreview';
import { MermaidChart, extractMermaidBlocks } from './MermaidChart';
import { EChartsChart } from './EChartsChart';
import { MapChart } from './MapChart';
import { extractArtifactBlocks } from './artifactUtils';
import Video from 'react-native-video';

// 图片查看器
interface ImageViewerProps {
  uri: string;
  visible: boolean;
  onClose: () => void;
}

function ImageViewer({ uri, visible, onClose }: ImageViewerProps) {
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

  return (
    <>
      <TouchableOpacity
        style={styles.imageContainer}
        onPress={() => setViewerVisible(true)}
      >
        <Image source={{ uri: url }} style={styles.image} resizeMode="cover" />
      </TouchableOpacity>
      <ImageViewer
        uri={url}
        visible={viewerVisible}
        onClose={() => setViewerVisible(false)}
      />
    </>
  );
}

// 文件消息组件
function FileMessage({ url }: { url: string }) {
  const { colors } = useTheme();
  const filename = decodeURIComponent(url.split('/').pop() || 'File');
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
          点击打开
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

// 主内容组件
interface MessageContentProps {
  content: string;
  isUser?: boolean;
}

export function MessageContent({ content, isUser = false }: MessageContentProps) {
  const { colors } = useTheme();

  if (typeof content !== 'string') {
    return (
      <Text style={{ color: colors.onSurface }}>
        {JSON.stringify(content, null, 2)}
      </Text>
    );
  }

  // 用 useMemo 缓存内容解析结果，避免每次渲染重复计算
  const parsedContent = useMemo(() => {
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

    // 分割内容：按 [Image:/File:/Audio:] 分割
    const parts = displayContent.split(
      /(\[(?:Image|File|Audio):\s*[^\]]+\]\([^)]+\)|\[(?:Image|File|Audio):\s*[^\]]+\])/g
    );

    return { displayContent, parts };
  }, [content]);

  const { parts } = parsedContent;

  // 获取 Markdown 样式
  const markdownStyles = useMemo(() => getMarkdownTheme(isUser, colors), [isUser, colors]);

  // 定义 Markdown 渲染规则
  const markdownRules = useMemo(() => ({
    // 处理代码块
    fence: (node: any) => (
      <CodeBlock
        key={node.key}
        code={node.content?.trim() || ''}
        language={node.attributes?.lang || 'text'}
      />
    ),
    code_block: (node: any) => (
      <CodeBlock
        key={node.key}
        code={node.content?.trim() || ''}
        language={node.attributes?.lang || 'text'}
      />
    ),
    // 禁用默认表格规则，我们目前使用手动解析和自定义组件
    table: () => null,
  }), []);

  return (
    <View style={styles.container}>
      {parts.map((part, index) => {
        // 匹配图片
        const imageMatch = part.match(/^\[Image:\s*([^\]]+)\]$/);
        if (imageMatch) {
          return <ImageMessage key={index} url={imageMatch[1]} />;
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

        // 渲染 Markdown 文本
        if (!part.trim()) return null;

        // 先提取 Artifact（如 ECharts 图表）
        const artifactParts = extractArtifactBlocks(part);

        return (
          <View key={index}>
            {artifactParts.map((aPart, aIndex) => {
              if (aPart.type === 'echarts') {
                return <EChartsChart key={aIndex} data={aPart.data} />;
              }
              if (aPart.type === 'map') {
                return <MapChart key={aIndex} data={aPart.data} />;
              }

              // 对文本部分继续提取 Mermaid 图表
              const mermaidParts = extractMermaidBlocks(aPart.content!);

              return (
                <View key={aIndex}>
                  {mermaidParts.map((mermaidPart, mIndex) => {
                    if (mermaidPart.type === 'mermaid') {
                      return <MermaidChart key={mIndex} chart={mermaidPart.content} />;
                    }

                    // 检查是否包含表格
                    const tableData = parseMarkdownTable(mermaidPart.content);
                    if (tableData && tableData.header.length > 0) {
                      return (
                        <MarkdownTable
                          key={mIndex}
                          header={tableData.header}
                          rows={tableData.rows}
                        />
                      );
                    }

                    // 统一使用 Markdown 渲染
                    return (
                      <Markdown
                        key={mIndex}
                        style={markdownStyles}
                        rules={markdownRules}
                      >
                        {mermaidPart.content}
                      </Markdown>
                    );
                  })}

                  {/* 链接预览 */}
                  <AutoLinkPreview text={aPart.content!} />
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
      fontSize: 15,
      lineHeight: 24, // 稍微增加行高提升可读性
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
});
