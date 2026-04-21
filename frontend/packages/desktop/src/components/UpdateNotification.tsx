/**
 * EvoLoop 更新通知组件
 * 
 * 显示更新提示，支持:
 * - 普通更新: 显示 "稍后提醒" 和 "立即更新" 按钮
 * - 强制更新: 只显示 "立即更新" 按钮，不能关闭
 */

import React, { useState } from 'react';
import { X, Download, AlertCircle, Sparkles, ChevronDown, ChevronUp } from 'lucide-react';
import { updateService } from '@/services/updateService';
import type { UpdateCheckResult } from '@/hooks/useVersion';

interface UpdateNotificationProps {
  updateInfo: UpdateCheckResult;
  onClose: () => void;
  onUpdate: () => void;
}

export const UpdateNotification: React.FC<UpdateNotificationProps> = ({
  updateInfo,
  onClose,
  onUpdate,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!updateInfo.hasUpdate) return null;

  const isForceUpdate = updateInfo.isForceUpdate;
  const latestVersion = updateInfo.latestVersion || '';

  const handleSkip = () => {
    updateService.skipVersion(latestVersion);
    onClose();
  };

  const handleUpdate = async () => {
    await updateService.reportUpdateStatus('download_start', latestVersion);
    onUpdate();
  };

  // 强制更新: 全屏遮罩，无法关闭
  if (isForceUpdate) {
    return (
      <div style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'rgba(0, 0, 0, 0.6)',
        backdropFilter: 'blur(4px)',
      }}>
        <div style={{
          width: '100%',
          maxWidth: '400px',
          padding: '32px',
          borderRadius: '16px',
          backgroundColor: '#fff',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
        }}>
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            marginBottom: '24px',
          }}>
            <div style={{
              width: '64px',
              height: '64px',
              borderRadius: '50%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: '#fef2f2',
            }}>
              <AlertCircle style={{ width: '32px', height: '32px', color: '#dc2626' }} />
            </div>
          </div>

          <h2 style={{
            marginBottom: '8px',
            textAlign: 'center',
            fontSize: '20px',
            fontWeight: 'bold',
            color: '#111827',
          }}>
            重要更新可用
          </h2>
          <p style={{
            marginBottom: '24px',
            textAlign: 'center',
            color: '#6b7280',
          }}>
            版本 {latestVersion} 包含重要修复，请立即更新以继续使用
          </p>

          {updateInfo.releaseNotes && (
            <div style={{
              maxHeight: '160px',
              overflowY: 'auto',
              marginBottom: '24px',
              padding: '16px',
              borderRadius: '8px',
              backgroundColor: '#f9fafb',
              fontSize: '14px',
              color: '#374151',
            }}>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
                {updateInfo.releaseNotes}
              </pre>
            </div>
          )}

          <button
            onClick={handleUpdate}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              width: '100%',
              padding: '12px 24px',
              borderRadius: '12px',
              border: 'none',
              fontSize: '16px',
              fontWeight: 500,
              color: '#fff',
              backgroundColor: '#2563eb',
              cursor: 'pointer',
            }}
          >
            <Download style={{ width: '20px', height: '20px' }} />
            立即更新
          </button>
        </div>
      </div>
    );
  }

  // 普通更新: 可关闭的通知卡片
  return (
    <div style={{
      position: 'fixed',
      bottom: '16px',
      right: '16px',
      zIndex: 9999,
      width: '100%',
      maxWidth: '360px',
      animation: 'slideUp 0.3s ease-out',
    }}>
      <div style={{
        borderRadius: '16px',
        backgroundColor: '#fff',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
        border: '1px solid #e5e7eb',
        overflow: 'hidden',
      }}>
        {/* 头部 */}
        <div style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px',
          padding: '16px',
        }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            backgroundColor: '#eff6ff',
            flexShrink: 0,
          }}>
            <Sparkles style={{ width: '20px', height: '20px', color: '#2563eb' }} />
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            <h3 style={{
              fontWeight: 600,
              color: '#111827',
              marginBottom: '4px',
            }}>
              发现新版本 {latestVersion}
            </h3>
            <p style={{
              fontSize: '14px',
              color: '#6b7280',
            }}>
              有新版本可用，是否立即更新？
            </p>
          </div>

          <button
            onClick={onClose}
            style={{
              padding: '4px',
              borderRadius: '8px',
              border: 'none',
              background: 'transparent',
              color: '#9ca3af',
              cursor: 'pointer',
            }}
          >
            <X style={{ width: '20px', height: '20px' }} />
          </button>
        </div>

        {/* 更新详情 */}
        {updateInfo.releaseNotes && isExpanded && (
          <div style={{
            borderTop: '1px solid #f3f4f6',
            padding: '12px 16px',
          }}>
            <div style={{
              maxHeight: '128px',
              overflowY: 'auto',
              fontSize: '14px',
              color: '#374151',
            }}>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>
                {updateInfo.releaseNotes}
              </pre>
            </div>
          </div>
        )}

        {/* 操作按钮 */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '12px 16px',
          borderTop: '1px solid #f3f4f6',
          backgroundColor: '#fafafa',
        }}>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '14px',
              color: '#6b7280',
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
            }}
          >
            {isExpanded ? <ChevronUp style={{ width: '16px', height: '16px' }} /> : <ChevronDown style={{ width: '16px', height: '16px' }} />}
            {isExpanded ? '收起' : '查看详情'}
          </button>

          <div style={{ flex: 1 }} />

          <button
            onClick={handleSkip}
            style={{
              padding: '6px 12px',
              borderRadius: '8px',
              border: 'none',
              fontSize: '14px',
              fontWeight: 500,
              color: '#6b7280',
              backgroundColor: 'transparent',
              cursor: 'pointer',
            }}
          >
            稍后提醒
          </button>

          <button
            onClick={handleUpdate}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 16px',
              borderRadius: '8px',
              border: 'none',
              fontSize: '14px',
              fontWeight: 500,
              color: '#fff',
              backgroundColor: '#2563eb',
              cursor: 'pointer',
            }}
          >
            <Download style={{ width: '16px', height: '16px' }} />
            立即更新
          </button>
        </div>
      </div>

      <style>{`
        @keyframes slideUp {
          from {
            opacity: 0;
            transform: translateY(20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
};

export default UpdateNotification;
