// 文件上传服务

import { api } from './client';
import i18n from '@/locales';

export interface UploadResponse {
  pic_path: string;
  pic_name: string;
  file_ext: string;
  pic_spec: string;
  update_time: number;
}

export interface UploadedFile {
  type: 'image' | 'video' | 'file';
  url: string;
  name: string;
  ext: string;
}

/**
 * 上传聊天图片
 * @param uri 本地图片 URI
 * @returns 上传后的图片信息
 */
export async function uploadChatImage(uri: string): Promise<UploadedFile> {
  // 创建 FormData
  const formData = new FormData();
  
  // 从 URI 获取文件名和类型
  const filename = uri.split('/').pop() || 'image.jpg';
  const match = /\.([a-zA-Z]+)$/.exec(filename);
  const ext = match ? match[1].toLowerCase() : 'jpg';
  
  // 根据扩展名判断 MIME 类型
  const mimeType = ext === 'mp4' || ext === 'mov' || ext === 'avi'
    ? `video/${ext === 'mov' ? 'quicktime' : ext}`
    : `image/${ext === 'jpg' ? 'jpeg' : ext}`;
  const fileType = mimeType.startsWith('video/') ? 'video' : 'image';
  
  // 添加文件到 FormData
  formData.append('file', {
    uri,
    name: filename,
    type: mimeType,
  } as any);

  const response = await api.post<any>(
    `/member/api/upload/chatimg`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );

  const data = response.data || response;
  
  if (data.code !== 0) {
    throw new Error(data.message || i18n.t('api.errors.uploadFailed'));
  }

  return {
    type: fileType as 'image' | 'video',
    url: data.data.pic_path,
    name: data.data.pic_name,
    ext: data.data.file_ext,
  };
}

/**
 * 上传聊天文件
 * @param uri 本地文件 URI
 * @param name 文件名
 * @returns 上传后的文件信息
 */
export async function uploadChatFile(uri: string, name: string): Promise<UploadedFile> {
  const formData = new FormData();
  
  // 获取文件扩展名
  const match = /\.([a-zA-Z]+)$/.exec(name);
  const ext = match ? match[1].toLowerCase() : '';
  
  // 支持的文件类型
  const supportedTypes = ['txt', 'xlsx', 'xls', 'csv', 'pem', 'doc', 'docx', 'pdf', 'md', 'json'];
  
  if (!supportedTypes.includes(ext)) {
    throw new Error(i18n.t('api.errors.unsupportedFileType', { ext, supportedTypes: supportedTypes.join(', ') }));
  }

  formData.append('file', {
    uri,
    name,
    type: 'application/octet-stream',
  } as any);

  const response = await api.post<any>(
    `/member/api/upload/chatfile`,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );

  const data = response.data || response;
  
  if (data.code !== 0) {
    throw new Error(data.message || i18n.t('api.errors.uploadFileFailed'));
  }

  return {
    type: 'file',
    url: data.data.pic_path,
    name: data.data.pic_name,
    ext: data.data.file_ext,
  };
}

/**
 * 批量上传聊天图片
 * @param uris 本地图片 URI 数组
 * @returns 上传后的图片信息数组
 */
export async function uploadChatImages(uris: string[]): Promise<UploadedFile[]> {
  const results: UploadedFile[] = [];
  
  for (const uri of uris) {
    try {
      const uploadedFile = await uploadChatImage(uri);
      results.push(uploadedFile);
    } catch (error) {
      console.error(`上传图片失败 ${uri}:`, error);
      // 继续上传其他图片
    }
  }
  
  return results;
}
