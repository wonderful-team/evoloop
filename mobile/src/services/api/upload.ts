// 文件上传服务

import { api } from './client';
import { MEMBER_API } from '@/constants/api';

export interface UploadResponse {
  pic_path: string;
  pic_name: string;
  file_ext: string;
  pic_spec: string;
  update_time: number;
}

export interface ChatAttachment {
  type: 'image' | 'file';
  url: string;
  name: string;
  ext: string;
}

/**
 * 上传聊天图片
 * @param uri 本地图片 URI
 * @returns 上传后的图片信息
 */
export async function uploadChatImage(uri: string): Promise<ChatAttachment> {
  // 创建 FormData
  const formData = new FormData();
  
  // 从 URI 获取文件名和类型
  const filename = uri.split('/').pop() || 'image.jpg';
  const match = /\.([a-zA-Z]+)$/.exec(filename);
  const ext = match ? match[1].toLowerCase() : 'jpg';
  
  // 添加文件到 FormData
  formData.append('file', {
    uri,
    name: filename,
    type: `image/${ext === 'jpg' ? 'jpeg' : ext}`,
  } as any);

  const response = await api.post<any>(
    MEMBER_API.UPLOAD_CHAT_IMAGE,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );

  const data = response.data || response;
  
  if (data.code !== 0) {
    throw new Error(data.message || '上传图片失败');
  }

  return {
    type: 'image',
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
export async function uploadChatFile(uri: string, name: string): Promise<ChatAttachment> {
  const formData = new FormData();
  
  // 获取文件扩展名
  const match = /\.([a-zA-Z]+)$/.exec(name);
  const ext = match ? match[1].toLowerCase() : '';
  
  // 支持的文件类型
  const supportedTypes = ['txt', 'xlsx', 'xls', 'csv', 'pem', 'doc', 'docx', 'pdf', 'md', 'json'];
  
  if (!supportedTypes.includes(ext)) {
    throw new Error(`不支持的文件类型: ${ext}。支持: ${supportedTypes.join(', ')}`);
  }

  formData.append('file', {
    uri,
    name,
    type: 'application/octet-stream',
  } as any);

  const response = await api.post<any>(
    MEMBER_API.UPLOAD_CHAT_FILE,
    formData,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    }
  );

  const data = response.data || response;
  
  if (data.code !== 0) {
    throw new Error(data.message || '上传文件失败');
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
export async function uploadChatImages(uris: string[]): Promise<ChatAttachment[]> {
  const results: ChatAttachment[] = [];
  
  for (const uri of uris) {
    try {
      const attachment = await uploadChatImage(uri);
      results.push(attachment);
    } catch (error) {
      console.error(`上传图片失败 ${uri}:`, error);
      // 继续上传其他图片
    }
  }
  
  return results;
}
