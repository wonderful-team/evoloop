// Artifacts 类型定义

/**
 * Artifact 类型
 */
export type ArtifactType = 
  | 'test_report' 
  | 'code_file' 
  | 'document' 
  | 'requirement_analysis'
  | 'diagram'
  | 'diff'
  | 'generic';

/**
 * Artifact 状态
 */
export type ArtifactStatus = 'generating' | 'completed' | 'failed';

/**
 * Artifact 基础信息
 */
export interface Artifact {
  id: string;
  type: ArtifactType;
  name: string;
  status: ArtifactStatus;
  created_at: string;
  updated_at: string;
  conversation_id: string;
  message_id?: string;
  metadata?: Record<string, any>;
}

/**
 * 测试报告 Artifact
 */
export interface TestReportArtifact extends Artifact {
  type: 'test_report';
  data: {
    total_tests: number;
    passed: number;
    failed: number;
    skipped: number;
    duration: number;
    suites: TestSuite[];
    summary: string;
  };
}

/**
 * 测试套件
 */
export interface TestSuite {
  name: string;
  tests: TestCase[];
  passed: number;
  failed: number;
  skipped: number;
}

/**
 * 测试用例
 */
export interface TestCase {
  name: string;
  status: 'passed' | 'failed' | 'skipped';
  duration: number;
  error?: string;
  output?: string;
}

/**
 * 代码文件 Artifact
 */
export interface CodeFileArtifact extends Artifact {
  type: 'code_file';
  data: {
    path: string;
    content: string;
    language: string;
    size: number;
  };
}

/**
 * 需求分析 Artifact
 */
export interface RequirementAnalysisArtifact extends Artifact {
  type: 'requirement_analysis';
  data: {
    analysis_id: string;
    document_id: string;
    project_id: number;
    summary: string;
    requirements: RequirementItem[];
    suggestions: string[];
  };
}

/**
 * 需求项
 */
export interface RequirementItem {
  id: string;
  title: string;
  description: string;
  priority: 'high' | 'medium' | 'low';
  type: 'functional' | 'non_functional';
  status: 'identified' | 'analyzed' | 'approved';
}

/**
 * Diff Artifact
 */
export interface DiffArtifact extends Artifact {
  type: 'diff';
  data: {
    path: string;
    diff: string;
    old_content?: string;
    new_content?: string;
    language?: string;
  };
}

/**
 * 文档 Artifact
 */
export interface DocumentArtifact extends Artifact {
  type: 'document';
  data: {
    title: string;
    content: string;
    format: 'markdown' | 'html' | 'text';
    toc?: TableOfContentItem[];
  };
}

/**
 * 目录项
 */
export interface TableOfContentItem {
  level: number;
  title: string;
  anchor: string;
}

/**
 * Artifact 列表响应
 */
export interface ArtifactListResponse {
  artifacts: Artifact[];
  total: number;
}

/**
 * Artifact 下载响应
 */
export interface ArtifactDownloadResponse {
  artifact_id: string;
  download_url: string;
  expires_at: string;
}
