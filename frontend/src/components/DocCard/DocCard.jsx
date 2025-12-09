import React from 'react';
import './DocCard.css';
import { formatDateKorean } from '../../utils/dateFormat';

/**
 * DocCard - 문서 카드 컴포넌트
 *
 * @param {Object} doc - 문서 정보
 * @param {string} doc.doc_id - 문서 ID
 * @param {string} doc.doc_title - 문서 제목
 * @param {string} doc.doc_type - 문서 유형
 * @param {string} doc.doc_url - 문서 URL
 * @param {string} doc.visibility - 공개 범위
 * @param {string} doc.owner_username - 업로더
 * @param {number} doc.chunk_count - 청크 수
 * @param {string} doc.uploaded_at - 업로드 시간
 * @param {string[]} doc.tags - 태그 목록
 * @param {string} doc.summary - 요약
 * @param {Function} onAskAboutDoc - 문서 기반 질문 콜백
 */
export default function DocCard({ doc, onAskAboutDoc }) {
  const handleViewDoc = () => {
    if (doc.doc_url) {
      window.open(doc.doc_url, '_blank');
    }
  };

  const handleAskQuestion = () => {
    if (onAskAboutDoc) {
      onAskAboutDoc(doc);
    }
  };

  return (
    <div className="doc-card">
      <div className="doc-card-header">
        <h3 className="doc-card-title" title={doc.doc_title}>
          {doc.doc_title || doc.doc_id}
        </h3>
        {doc.visibility && (
          <span className={`doc-card-badge visibility-${doc.visibility}`}>
            {doc.visibility === 'public' ? '공개' :
             doc.visibility === 'org' ? '조직' : '비공개'}
          </span>
        )}
      </div>

      <div className="doc-card-meta">
        {doc.doc_type && (
          <span className="doc-card-type">{doc.doc_type}</span>
        )}
        {doc.owner_username && (
          <span className="doc-card-owner">업로더: {doc.owner_username}</span>
        )}
        {doc.uploaded_at && (
          <span className="doc-card-date">{formatDateKorean(doc.uploaded_at)}</span>
        )}
      </div>

      {doc.summary && (
        <p className="doc-card-summary">{doc.summary}</p>
      )}

      {doc.tags && doc.tags.length > 0 && (
        <div className="doc-card-tags">
          {doc.tags.map((tag, idx) => (
            <span key={idx} className="doc-card-tag">
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="doc-card-footer">
        <span className="doc-card-chunks">{doc.chunk_count || 0} 청크</span>
        <div className="doc-card-actions">
          {doc.doc_url && (
            <button
              className="doc-card-btn doc-card-btn-view"
              onClick={handleViewDoc}
              title="문서 보기"
            >
              📄 보기
            </button>
          )}
          <button
            className="doc-card-btn doc-card-btn-ask"
            onClick={handleAskQuestion}
            title="이 문서에 대해 질문하기"
          >
            💬 질문하기
          </button>
        </div>
      </div>
    </div>
  );
}
