// 代码块组件 - 支持语法高亮和复制

import React, { useState, useCallback } from 'react';
import { View, StyleSheet, TouchableOpacity, LogBox } from 'react-native';
import { Text, IconButton, Menu } from 'react-native-paper';

// 屏蔽第三方库陈旧代码导致的警告
LogBox.ignoreLogs(['NativeSyntaxHighlighter: Support for defaultProps']);

import SyntaxHighlighter from 'react-native-syntax-highlighter';

// 尝试使用更通用的兼容路径
import { atomOneDark, github } from 'react-syntax-highlighter/dist/styles/hljs';
import { useTheme } from '@/theme';


import Clipboard from '@react-native-clipboard/clipboard';
import { shareCodeBlock } from '@/utils/share';
import { useTranslation } from 'react-i18next';

interface CodeBlockProps {
  code: string;
  language?: string;
  showLineNumbers?: boolean;
}

// 语言映射
const languageMap: Record<string, string> = {
  js: 'javascript',
  jsx: 'javascript',
  ts: 'typescript',
  tsx: 'typescript',
  py: 'python',
  rb: 'ruby',
  go: 'go',
  rs: 'rust',
  java: 'java',
  kt: 'kotlin',
  swift: 'swift',
  cpp: 'cpp',
  c: 'c',
  cs: 'csharp',
  php: 'php',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  sql: 'sql',
  json: 'json',
  xml: 'xml',
  html: 'html',
  css: 'css',
  scss: 'scss',
  sass: 'scss',
  less: 'less',
  md: 'markdown',
  yml: 'yaml',
  yaml: 'yaml',
  dockerfile: 'dockerfile',
  docker: 'dockerfile',
  graphql: 'graphql',
  gql: 'graphql',
  vue: 'html',
  svelte: 'html',
  angular: 'typescript',
};

// react-native-syntax-highlighter / prism 支持的语言白名单
// 注意：'text' 不在 Prism 支持列表中，传进去会导致 Object.keys(undefined) 崩溃
// 不在白名单中的语言直接渲染纯文本，不调用 SyntaxHighlighter
const SUPPORTED_LANGUAGES = new Set([
  'javascript', 'typescript', 'python', 'java', 'kotlin', 'swift',
  'go', 'rust', 'cpp', 'c', 'csharp', 'php', 'bash', 'sql', 'json',
  'xml', 'html', 'css', 'scss', 'less', 'markdown', 'yaml', 'dockerfile',
  'graphql', 'ruby',
]);

export function CodeBlock({ code, language = 'text', showLineNumbers = false }: CodeBlockProps) {
  const { t } = useTranslation();
  const { colors, isDark } = useTheme();
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);

  
  // 防御：language 可能为 undefined 或空字符串
  const safeLanguage = (language || '').toLowerCase();
  const mappedLang = languageMap[safeLanguage] || safeLanguage;
  // 只有白名单内的语言才使用 SyntaxHighlighter，否则渲染纯文本
  const normalizedLang = SUPPORTED_LANGUAGES.has(mappedLang) ? mappedLang : null;
  
  // 判断是否展开（代码超过10行时）
  const lineCount = code.split('\n').length;
  const shouldCollapse = lineCount > 10 && !expanded;
  const displayCode = shouldCollapse 
    ? code.split('\n').slice(0, 10).join('\n') + '\n...'
    : code;

  const handleCopy = useCallback(() => {
    Clipboard.setString(code);
    setCopied(true);
    setMenuVisible(false);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  const handleCopyWithoutFormat = useCallback(() => {
    // 移除代码中的格式，只保留纯文本
    const plainText = code
      .replace(/```[\w]*\n?/g, '')
      .replace(/```/g, '')
      .trim();
    Clipboard.setString(plainText);
    setCopied(true);
    setMenuVisible(false);
    setTimeout(() => setCopied(false), 2000);
  }, [code]);

  const handleShare = useCallback(async () => {
    await shareCodeBlock(code, language);
    setMenuVisible(false);
  }, [code, language]);

  return (
    <View style={[styles.container, { backgroundColor: colors.surfaceVariant }]}>
      {/* 头部：语言标识和操作按钮 */}
      <View style={[styles.header, { borderBottomColor: colors.outline + '30' }]}>
        <View style={styles.headerLeft}>
          <Text style={[styles.language, { color: colors.primary }]}>
            {language.toUpperCase() || 'TEXT'}
          </Text>
          {lineCount > 10 && (
            <Text style={[styles.lineCount, { color: colors.onSurfaceVariant }]}>
              {lineCount} {t('codeBlock.lines')}
            </Text>
          )}
        </View>
        
        <View style={styles.headerRight}>
          {copied ? (
            <Text style={[styles.copiedText, { color: colors.primary }]}>{t('codeBlock.copied')}</Text>
          ) : (
            <Menu
              visible={menuVisible}
              onDismiss={() => setMenuVisible(false)}
              anchor={
                <IconButton
                  icon="dots-vertical"
                  size={18}
                  iconColor={colors.onSurfaceVariant}
                  onPress={() => setMenuVisible(true)}
                />
              }
            >
              <Menu.Item
                onPress={handleCopy}
                title={t('chat.codeBlock.copyCode')}
                leadingIcon="content-copy"
              />
              <Menu.Item
                onPress={handleCopyWithoutFormat}
                title={t('chat.codeBlock.copyText')}
                leadingIcon="format-clear"
              />
              <Menu.Item
                onPress={handleShare}
                title={t('chat.codeBlock.share')}
                leadingIcon="share-variant"
              />
            </Menu>
          )}
          <IconButton
            icon={copied ? 'check' : 'content-copy'}
            size={18}
            iconColor={copied ? colors.primary : colors.onSurfaceVariant}
            onPress={handleCopy}
          />
        </View>
      </View>

      {/* 代码内容：白名单内语言用 SyntaxHighlighter，其他纯文本 */}
      <View style={styles.codeWrapper}>
        {normalizedLang ? (
          <SyntaxHighlighter
            language={normalizedLang}
            style={atomOneDark}
            customStyle={{


              backgroundColor: 'transparent',
              padding: 0,
              margin: 0,
            }}
            codeTagProps={{
              style: {
                fontFamily: 'monospace',
                fontSize: 13,
                lineHeight: 20,
              },
            }}
          >
            {displayCode}
          </SyntaxHighlighter>
        ) : (
          <Text
            selectable
            style={[
              styles.plainCode,
              { color: colors.onSurface, fontFamily: 'monospace', fontSize: 13, lineHeight: 20 },
            ]}
          >
            {displayCode}
          </Text>
        )}
      </View>

      {/* 展开/收起按钮 */}
      {lineCount > 10 && (
        <TouchableOpacity
          style={[styles.expandButton, { borderTopColor: colors.outline + '30' }]}
          onPress={() => setExpanded(!expanded)}
        >
          <Text style={[styles.expandText, { color: colors.primary }]}>
            {expanded ? t('chat.codeBlock.collapse') : t('chat.codeBlock.expandAll', { count: lineCount })}
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );
}

// 行内代码组件
interface InlineCodeProps {
  code: string;
  isUser?: boolean;
}

export function InlineCode({ code, isUser }: InlineCodeProps) {
  const { colors } = useTheme();
  
  return (
    <Text
      style={[
        styles.inlineCode,
        {
          backgroundColor: isUser ? 'rgba(0,0,0,0.1)' : colors.surfaceVariant,
          color: isUser ? colors.onPrimaryContainer : colors.onSurface,
        },
      ]}
    >
      {code}
    </Text>
  );
}

const styles = StyleSheet.create({
  container: {
    borderRadius: 12,
    marginVertical: 8,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  language: {
    fontSize: 11,
    fontWeight: '600',
    fontFamily: 'monospace',
  },
  lineCount: {
    fontSize: 11,
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  copiedText: {
    fontSize: 12,
    marginRight: 8,
  },
  codeWrapper: {
    padding: 12,
  },
  expandButton: {
    alignItems: 'center',
    paddingVertical: 10,
    borderTopWidth: 1,
  },
  expandText: {
    fontSize: 13,
    fontWeight: '500',
  },
  inlineCode: {
    paddingHorizontal: 5,
    paddingVertical: 2,
    borderRadius: 4,
    fontFamily: 'monospace',
    fontSize: 13,
  },
  plainCode: {
    fontFamily: 'monospace',
    fontSize: 13,
    lineHeight: 20,
  },
});
