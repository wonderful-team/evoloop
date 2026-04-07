// Artifacts API

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
 */
export async function getConversationArtifacts(
  conversationId: string,
  type?: string
): Promise<ArtifactListResponse> {
  const params = new URLSearchParams();
  if (type) params.append('type', type);
  
  const response = await api.get(
    `${MEMBER_API.CONVERSATIONS}/${conversationId}/artifacts?${params.toString()}`
  );
  return response.data;
}

/**
 * 获取 Artifact 详情
 */
export async function getArtifact(artifactId: string): Promise<Artifact> {
  const response = await api.get(`${MEMBER_API.ARTIFACTS}/${artifactId}`);
  return response.data;
}

/**
 * 获取测试报告 Artifact
 */
export async function getTestReportArtifact(
  artifactId: string
): Promise<TestReportArtifact> {
  const response = await api.get(`${MEMBER_API.ARTIFACTS}/${artifactId}/test-report`);
  return response.data;
}

/**
 * 获取代码文件 Artifact
 */
export async function getCodeFileArtifact(
  artifactId: string
): Promise<CodeFileArtifact> {
  const response = await api.get(`${MEMBER_API.ARTIFACTS}/${artifactId}/code-file`);
  return response.data;
}

/**
 * 获取需求分析 Artifact
 */
export async function getRequirementAnalysisArtifact(
  artifactId: string
): Promise<RequirementAnalysisArtifact> {
  const response = await api.get(
    `${MEMBER_API.ARTIFACTS}/${artifactId}/requirement-analysis`
  );
  return response.data;
}

/**
 * 获取 Diff Artifact
 */
export async function getDiffArtifact(
  artifactId: string
): Promise<DiffArtifact> {
  const response = await api.get(`${MEMBER_API.ARTIFACTS}/${artifactId}/diff`);
  return response.data;
}

/**
 * 获取 Artifact 下载链接
 */
export async function getArtifactDownloadUrl(
  artifactId: string
): Promise<ArtifactDownloadResponse> {
  const response = await api.get(`${MEMBER_API.ARTIFACTS}/${artifactId}/download`);
  return response.data;
}

/**
 * 下载 Artifact 内容
 */
export async function downloadArtifact(artifactId: string): Promise<Blob> {
  const response = await api.get(`${MEMBER_API.ARTIFACTS}/${artifactId}/content`, {
    responseType: 'blob',
  });
  return response.data;
}

/**
 * 删除 Artifact
 */
export async function deleteArtifact(artifactId: string): Promise<void> {
  await api.delete(`${MEMBER_API.ARTIFACTS}/${artifactId}`);
}

/**
 * 获取项目的 Artifacts
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
    `${MEMBER_API.PROJECTS}/${projectId}/artifacts?${params.toString()}`
  );
  return response.data;
}
