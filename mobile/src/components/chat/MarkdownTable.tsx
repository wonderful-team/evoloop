// Markdown 表格组件 - 支持横向滚动

import React from 'react';
import {
  View,
  StyleSheet,
  ScrollView,
  useWindowDimensions,
} from 'react-native';
import { Text } from 'react-native-paper';
import { useTheme } from '@/theme';

interface TableCell {
  content: string;
  isHeader?: boolean;
}

interface TableRow {
  cells: TableCell[];
  isHeader?: boolean;
}

interface MarkdownTableProps {
  header: string[];
  rows: string[][];
}

export function MarkdownTable({ header, rows }: MarkdownTableProps) {
  const { colors } = useTheme();
  const { width: windowWidth } = useWindowDimensions();
  
  // 计算最小列宽
  const minColWidth = 80;
  const maxColWidth = 200;
  const estimatedColWidth = Math.min(
    maxColWidth,
    Math.max(minColWidth, (windowWidth - 48) / header.length)
  );
  
  const tableWidth = header.length * estimatedColWidth;
  const needsScroll = tableWidth > windowWidth - 32;

  const renderCell = (content: string, isHeader: boolean, colIndex: number) => (
    <View
      key={colIndex}
      style={[
        styles.cell,
        {
          width: estimatedColWidth,
          backgroundColor: isHeader ? colors.surfaceVariant : 'transparent',
          borderRightWidth: colIndex < header.length - 1 ? 1 : 0,
          borderRightColor: colors.outline + '40',
        },
      ]}
    >
      <Text
        style={[
          styles.cellText,
          {
            fontWeight: isHeader ? '700' : '400',
            color: isHeader ? colors.primary : colors.onSurface,
          },
        ]}
        numberOfLines={3}
      >
        {content}
      </Text>
    </View>
  );

  const TableContent = () => (
    <View
      style={[
        styles.table,
        {
          borderColor: colors.outline,
          width: needsScroll ? tableWidth : '100%',
        },
      ]}
    >
      {/* 表头 */}
      <View style={styles.row}>
        {header.map((cell, index) => renderCell(cell, true, index))}
      </View>
      
      {/* 数据行 */}
      {rows.map((row, rowIndex) => (
        <View
          key={rowIndex}
          style={[
            styles.row,
            {
              borderTopWidth: 1,
              borderTopColor: colors.outline + '40',
              backgroundColor: rowIndex % 2 === 1 ? colors.surfaceVariant + '30' : 'transparent',
            },
          ]}
        >
          {row.map((cell, colIndex) => renderCell(cell, false, colIndex))}
        </View>
      ))}
    </View>
  );

  return (
    <View style={styles.container}>
      {needsScroll ? (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={true}
          contentContainerStyle={styles.scrollContent}
        >
          <TableContent />
        </ScrollView>
      ) : (
        <TableContent />
      )}
    </View>
  );
}

// 解析 Markdown 表格文本
export function parseMarkdownTable(text: string): MarkdownTableProps | null {
  const lines = text.trim().split('\n').filter(line => line.trim());
  
  // 至少需要两行：表头和分隔符
  if (lines.length < 2) return null;
  
  // 解析表头
  const headerLine = lines[0];
  const header = headerLine
    .split('|')
    .map(cell => cell.trim())
    .filter(cell => cell);
  
  if (header.length === 0) return null;
  
  // 跳过分隔符行（第二行，包含 ---）
  const dataLines = lines.slice(2);
  
  // 解析数据行
  const rows = dataLines.map(line =>
    line
      .split('|')
      .map(cell => cell.trim())
      .filter((_, index, arr) => index > 0 && index < arr.length - 1) // 移除首尾空单元格
  ).filter(row => row.length > 0);
  
  return { header, rows };
}

const styles = StyleSheet.create({
  container: {
    marginVertical: 12,
  },
  scrollContent: {
    paddingRight: 8,
  },
  table: {
    borderWidth: 1,
    borderRadius: 8,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
  },
  cell: {
    padding: 10,
    justifyContent: 'center',
  },
  cellText: {
    fontSize: 13,
    lineHeight: 18,
  },
});
