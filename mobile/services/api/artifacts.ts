// Artifacts API - 通过 Gateway 访问
// 链路: Mobile → Gateway (evoloop/backend) → 文件/Artifact 服务

import { api } from './client';
import { GATEWAY_API } from '@/constants/api';
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
 * GET /gateway/api/v1/conversations/:id/artifacts
 */
export async function getConversationArtifacts(
  conversationId: string,
  type?: string
): Promise<ArtifactListResponse> {
  const params = new URLSearchParams();
  if (type) params.append('type', type);
  
  const response = await api.get(
    `${GATEWAY_API.CONVERSATION_DETAIL(conversationId)}/artifacts?${params.toString()}`
  );
  return response.data;
}

/**
 * 获取 Artifact 详情
 * GET /gateway/api/v1/artifacts/:id
 */
export async function getArtifact(artifactId: string): Promise<Artifact> {
  const response = await api.get(GATEWAY_API.ARTIFACT_DETAIL(artifactId));
  return response.data;
}

/**
 * 获取测试报告 Artifact
 * GET /gateway/api/v1/artifacts/:id/test-report
 */
export async function getTestReportArtifact(
  artifactId: string
): Promise<TestReportArtifact> {
  const response = await api.get(`${GATEWAY_API.ARTIFACT_DETAIL(artifactId)}/test-report`);
  return response.data;
}

/**
 * 获取代码文件 Artifact
 * GET /gateway/api/v1/artifacts/:id/code-file
 */
export async function getCodeFileArtifact(
  artifactId: string
): Promise<CodeFileArtifact> {
  const response = await api.get(`${GATEWAY_API.ARTIFACT_DETAIL(artifactId)}/code-file`);
  return response.data;
}

/**
 * 获取需求分析 Artifact
 * GET /gateway/api/v1/artifacts/:id/requirement-analysis
 */
export async function getRequirementAnalysisArtifact(
  artifactId: string
): Promise<RequirementAnalysisArtifact> {
  const response = await api.get(
    `${GATEWAY_API.ARTIFACT_DETAIL(artifactId)}/requirement-analysis`
  );
  return response.data;
}

/**
 * 获取 Diff Artifact
 * GET /gateway/api/v1/artifacts/:id/diff
 */
export async function getDiffArtifact(
  artifactId: string
): Promise<DiffArtifact> {
  const response = await api.get(`${GATEWAY_API.ARTIFACT_DETAIL(artifactId)}/diff`);
  return response.data;
}

/**
 * 获取 Artifact 下载链接
 * GET /gateway/api/v1/artifacts/:id/download
 */
export async function getArtifactDownloadUrl(
  artifactId: string
): Promise<ArtifactDownloadResponse> {
  const response = await api.get(`${GATEWAY_API.ARTIFACT_DETAIL(artifactId)}/download`);
  return response.data;
}

/**
 * 下载 Artifact 内容
 * GET /gateway/api/v1/artifacts/:id/content
 */
export async function downloadArtifact(artifactId: string): Promise<Blob> {
  const response = await api.get(`${GATEWAY_API.ARTIFACT_DETAIL(artifactId)}/content`, {
    responseType: 'blob',
  });
  return response.data;
}

/**
 * 删除 Artifact
 * DELETE /gateway/api/v1/artifacts/:id
 */
export async function deleteArtifact(artifactId: string): Promise<void> {
  await api.delete(GATEWAY_API.ARTIFACT_DETAIL(artifactId));
}

/**
 * 获取项目的 Artifacts
 * GET /gateway/api/v1/projects/:id/artifacts
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
    `${GATEWAY_API.PROJECT_DETAIL(projectId)}/artifacts?${params.toString()}`
  );
  return response.data;
}
