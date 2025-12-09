import React, { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { FaLock } from 'react-icons/fa';

import { docsApi } from '../api/http';
import { me as fetchMe } from '../store/auth';
import { fmtDate } from '../utils/dateFormat';

import LoadingSpinner, { CardLoader } from '../components/LoadingSpinner/LoadingSpinner';

import './DocsPage.css';

// 상수 정의
const DOCS_LOAD_LIMIT = 200; // 문서 목록 로드 최대 개수

export default function DocsPage() {
  const navigate = useNavigate();

  // 사용자 상태
  const [user, setUser] = useState(null);
  const [userLoading, setUserLoading] = useState(true);
  const isLoggedIn = !!user;

  // 상태
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // 필터 상태 (심플하게)
  const [qTitle, setQTitle] = useState('');
  const [qUploader, setQUploader] = useState('');

  // 챗봇 사서 상태
  const [librarianQuery, setLibrarianQuery] = useState('');
  const [librarianLoading, setLibrarianLoading] = useState(false);
  const [selectedDocIds, setSelectedDocIds] = useState([]); // 챗봇 사서로 선택된 문서 ID
  const [librarianResponse, setLibrarianResponse] = useState(null); // 챗봇 사서 응답

  // 문서 로드
  const loadDocs = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await docsApi.search({
        limit: DOCS_LOAD_LIMIT,
      });
      setDocs(response.items || []);
    } catch (err) {
      setError(err.message || '문서를 불러올 수 없습니다.');
    } finally {
      setLoading(false);
    }
  };

  // 사용자 정보 로드 및 인증 이벤트 리스너
  useEffect(() => {
    (async () => {
      setUserLoading(true);
      try {
        setUser(await fetchMe());
      } catch {
        setUser(null);
      } finally {
        setUserLoading(false);
      }
    })();

    // 로그인/로그아웃 시 페이지 새로고침
    const onAuthChanged = () => window.location.reload();
    const onStorage = (e) => {
      if (e.key === 'auth_token') onAuthChanged();
    };
    window.addEventListener('auth:changed', onAuthChanged);
    window.addEventListener('storage', onStorage);

    return () => {
      window.removeEventListener('auth:changed', onAuthChanged);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  // 로그인된 경우에만 문서 로드
  useEffect(() => {
    if (isLoggedIn) {
      loadDocs();
    }
  }, [isLoggedIn]);

  // 필터 적용
  const filtered = useMemo(() => {
    let result = docs || [];

    // 1) 챗봇 사서로 선택된 문서가 있으면 그것만 표시
    if (selectedDocIds.length > 0) {
      result = result.filter(doc => selectedDocIds.includes(doc.doc_id));
    }

    // 2) 일반 필터 (제목, 업로더)
    const t = (qTitle || '').trim().toLowerCase();
    const u = (qUploader || '').trim().toLowerCase();
    if (t || u) {
      result = result.filter((doc) => {
        const title = (doc.doc_title || doc.doc_id || '').toLowerCase();
        const uploader = (doc.owner_username || '').toLowerCase();
        return (!t || title.includes(t)) && (!u || uploader.includes(u));
      });
    }

    return result;
  }, [docs, qTitle, qUploader, selectedDocIds]);

  // 문서 요약 (QueryPage로 이동)
  const handleSummarize = (doc) => {
    navigate('/', {
      state: {
        docId: doc.doc_id,
        docTitle: doc.doc_title,
        initialQuestion: `"${doc.doc_title}" 문서의 내용을 요약해주세요.`,
      },
    });
  };

  // 챗봇 사서 (자연어로 문서 검색)
  const handleLibrarianSearch = async () => {
    if (!librarianQuery.trim()) return;

    setLibrarianLoading(true);
    setLibrarianResponse(null); // 이전 응답 초기화
    try {
      // LLM API 호출하여 적합한 문서 선택
      const result = await docsApi.librarian(librarianQuery);

      if (result.selected_doc_ids && result.selected_doc_ids.length > 0) {
        // 선택된 문서 ID 저장
        setSelectedDocIds(result.selected_doc_ids);

        // 일반 필터 초기화
        setQTitle('');
        setQUploader('');

        // 응답 저장
        setLibrarianResponse({
          success: true,
          titles: result.selected_titles,
          explanation: result.explanation,
        });
      } else {
        setLibrarianResponse({
          success: false,
          explanation: result.explanation || '적합한 문서를 찾지 못했습니다. 다른 검색어로 시도해보세요.',
        });
      }
    } catch (err) {
      setLibrarianResponse({
        success: false,
        explanation: '검색 실패: ' + (err.message || '알 수 없는 오류'),
      });
    } finally {
      setLibrarianLoading(false);
    }
  };

  // 필터 초기화
  const handleResetFilters = () => {
    setQTitle('');
    setQUploader('');
    setSelectedDocIds([]);
    setLibrarianQuery('');
    setLibrarianResponse(null);
  };

  // 사용자 정보 로딩 중
  if (userLoading) {
    return (
      <div className="docs-page">
        <div className="docs-page-header">
          <h2>문서 열람</h2>
          <p className="docs-page-desc">전체 문서를 조회/검색하고 요약을 확인할 수 있습니다.</p>
        </div>
        <CardLoader message="사용자 정보 확인 중..." />
      </div>
    );
  }

  return (
    <div className="docs-page">
      <div className="docs-page-header">
        <h2>문서 열람</h2>
        <p className="docs-page-desc">전체 문서를 조회/검색하고 요약을 확인할 수 있습니다.</p>
      </div>

      {/* 로그인 가드 배너 */}
      {!isLoggedIn && (
        <div className="guard-banner">
          <FaLock />
          <div>
            <strong>로그인이 필요합니다.</strong>
            <div>로그인 후 문서 열람 기능을 이용할 수 있어요.</div>
          </div>
        </div>
      )}

      {/* 콘텐츠 래퍼 (비로그인 시 블러 처리) */}
      <div className={`docs-content-wrap ${!isLoggedIn ? 'is-disabled' : ''}`}>
        {/* 비로그인 시 블러 오버레이 */}
        {!isLoggedIn && (
          <div className="blocked-overlay">
            <FaLock />
            <div className="blocked-text">로그인 후 이용 가능합니다</div>
          </div>
        )}

        {/* 챗봇 사서 */}
        <div className="docs-librarian">
        <div className="docs-librarian-header">
          <h3>📚 챗봇 사서</h3>
          <p>원하는 문서를 찾아보세요. 예: "연차 신청하려고 하는데 참고할만한 문서를 찾아"</p>
        </div>
        <div className="docs-librarian-search">
          <input
            type="text"
            className="docs-librarian-input"
            placeholder="찾고 싶은 문서에 대해 질문해보세요"
            value={librarianQuery}
            onChange={(e) => setLibrarianQuery(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleLibrarianSearch()}
            disabled={librarianLoading}
          />
          <button
            className={`docs-librarian-btn ${librarianLoading ? 'is-loading' : ''}`}
            onClick={handleLibrarianSearch}
            disabled={librarianLoading || !librarianQuery.trim()}
          >
            {librarianLoading ? (
              <>
                <LoadingSpinner size="sm" color="white" inline />
                <span>검색 중</span>
              </>
            ) : '검색'}
          </button>
        </div>

        {/* 챗봇 사서 응답 풍선 */}
        {librarianResponse && (
          <div className={`docs-librarian-bubble ${librarianResponse.success ? 'success' : 'error'}`}>
            <button
              className="docs-librarian-bubble-close"
              onClick={() => setLibrarianResponse(null)}
              aria-label="닫기"
            >
              ×
            </button>
            {librarianResponse.success ? (
              <>
                <div className="docs-librarian-bubble-title">✅ 찾았습니다!</div>
                <div className="docs-librarian-bubble-content">
                  <strong>선택된 문서:</strong> {librarianResponse.titles.join(', ')}
                </div>
                <div className="docs-librarian-bubble-explanation">
                  {librarianResponse.explanation}
                </div>
              </>
            ) : (
              <>
                <div className="docs-librarian-bubble-title">❌ 문서를 찾지 못했습니다</div>
                <div className="docs-librarian-bubble-explanation">
                  {librarianResponse.explanation}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* 일반 필터 */}
      <div className="docs-filters">
        <div className="docs-filter">
          <label>문서명</label>
          <input
            type="text"
            placeholder="문서명 검색"
            value={qTitle}
            onChange={(e) => setQTitle(e.target.value)}
          />
        </div>
        <div className="docs-filter">
          <label>업로더</label>
          <input
            type="text"
            placeholder="업로더 검색"
            value={qUploader}
            onChange={(e) => setQUploader(e.target.value)}
          />
        </div>
        <div className="docs-filter">
          <button
            className="btn btn-reset"
            onClick={handleResetFilters}
            title="모든 필터 초기화"
          >
            초기화
          </button>
        </div>
      </div>

      {error && <div className="docs-error">{error}</div>}

      {loading ? (
        <CardLoader message="문서 목록을 불러오는 중..." icon="📚" />
      ) : filtered.length === 0 ? (
        <div className="docs-empty">표시할 문서가 없습니다.</div>
      ) : (
        <div className="docs-table-wrap">
          <table className="docs-table">
            <thead>
              <tr>
                <th className="col-index">#</th>
                <th>문서명</th>
                <th className="col-uploader">업로더</th>
                <th className="col-date">업로드 날짜</th>
                <th className="col-vis">가시성</th>
                <th className="col-chunks">청크수</th>
                <th className="col-preview">미리보기</th>
                <th className="col-actions">요약</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((doc, idx) => (
                <tr key={doc.doc_id}>
                  <td className="col-index">{idx + 1}</td>
                  <td title={doc.doc_id}>
                    <div className="docs-title">{doc.doc_title || doc.doc_id}</div>
                    <div className="docs-sub">doc_id: {doc.doc_id}</div>
                  </td>
                  <td className="col-uploader">
                    <div>@{doc.owner_username || '-'}</div>
                  </td>
                  <td className="docs-muted col-date">
                    {fmtDate(doc.uploaded_at)}
                  </td>
                  <td className="col-vis">{doc.visibility || '-'}</td>
                  <td className="col-chunks">{doc.chunk_count ?? 0}</td>
                  <td className="col-preview">
                    {doc.doc_url ? (
                      <a href={doc.doc_url} target="_blank" rel="noreferrer">
                        열기
                      </a>
                    ) : (
                      <span className="docs-sub">URL 없음</span>
                    )}
                  </td>
                  <td className="col-actions">
                    <button
                      className="btn btn-primary"
                      onClick={() => handleSummarize(doc)}
                    >
                      요약
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      </div>
    </div>
  );
}
