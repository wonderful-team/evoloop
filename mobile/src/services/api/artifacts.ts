// Artifacts API
// 架构：Mobile → MC (Member Center 存储)

import { api } from './client';
import { MEMBER_API } from '@/constants/api';
import {
  Artifact,
  ArtifactListResponse,
  ArtifactDownloadResponse,
  TestReportArtifact,
  CodeFileArtifact,
  RequirementAnalysisArtifact,
  DiffArtifact,
} from '@/types/artifact';

/**
 * 获取会话的 Artifacts
 * GET /member/api/conversations/:id/artifacts
 */
export async function getConversationArtifacts(
  conversationId: string,
  type?: string
): Promise<ArtifactListResponse> {
  const params = new URLSearchParams();
  if (type) params.append('type', type);
  
  const response = await api.get(
    `${MEMBER_API.CONVERSATION_DETAIL(conversationId)}/artifacts?${params.toString()}`
  );
  return response.data;
}

/**
 * 获取 Artifact 详情
 * GET /member/api/artifacts/:id
 */
export async function getArtifact(artifactId: string): Promise<Artifact> {
  const response = await api.get(MEMBER_API.ARTIFACT_DETAIL(artifactId));
  return response.data;
}

/**
 * 获取测试报告 Artifact
 * GET /member/api/artifacts/:id/test-report
 */
export async function getTestReportArtifact(
  artifactId: string
): Promise<TestReportArtifact> {
  const response = await api.get(`${MEMBER_API.ARTIFACT_DETAIL(artifactId)}/test-report`);
  return response.data;
}

/**
 * 获取代码文件 Artifact
 * GET /member/api/artifacts/:id/code-file
 */
export async function getCodeFileArtifact(
  artifactId: string
): Promise<CodeFileArtifact> {
  const response = await api.get(`${MEMBER_API.ARTIFACT_DETAIL(artifactId)}/code-file`);
  return response.data;
}

/**
 * 获取需求分析 Artifact
 * GET /member/api/artifacts/:id/requirement-analysis
 */
export async function getRequirementAnalysisArtifact(
  artifactId: string
): Promise<RequirementAnalysisArtifact> {
  const response = await api.get(
    `${MEMBER_API.ARTIFACT_DETAIL(artifactId)}/requirement-analysis`
  );
  return response.data;
}

/**
 * 获取 Diff Artifact
 * GET /member/api/artifacts/:id/diff
 */
export async function getDiffArtifact(
  artifactId: string
): Promise<DiffArtifact> {
  const response = await api.get(`${MEMBER_API.ARTIFACT_DETAIL(artifactId)}/diff`);
  return response.data;
}

/**
 * 获取 Artifact 下载链接
 * GET /member/api/artifacts/:id/download
 */
export async function getArtifactDownloadUrl(
  artifactId: string
): Promise<ArtifactDownloadResponse> {
  const response = await api.get(`${MEMBER_API.ARTIFACT_DETAIL(artifactId)}/download`);
  return response.data;
}

/**
 * 下载 Artifact 内容
 * GET /member/api/artifacts/:id/content
 */
export async function downloadArtifact(artifactId: string): Promise<Blob> {
  const response = await api.get(`${MEMBER_API.ARTIFACT_DETAIL(artifactId)}/content`, {
    responseType: 'blob',
  });
  return response.data;
}

/**
 * 删除 Artifact
 * DELETE /member/api/artifacts/:id
 */
export async function deleteArtifact(artifactId: string): Promise<void> {
  await api.delete(MEMBER_API.ARTIFACT_DETAIL(artifactId));
}

/**
 * 获取项目的 Artifacts
 * GET /member/api/projects/:id/artifacts
 */
export async function getProjectArtifacts(
  projectId: number,
  options?: {
    type?: string;
    page?: number;
    pageSize?: number;
  }
): Promise<ArtifactListResponse> {
  const params = new URLSearchParams();
  if (options?.type) params.append('type', options.type);
  if (options?.page) params.append('page', options.page.toString());
  if (options?.pageSize) params.append('page_size', options.pageSize.toString());
  
  const response = await api.get(
    `${MEMBER_API.PROJECT_DETAIL(projectId)}/artifacts?${params.toString()}`
  );
  return response.data;
}
