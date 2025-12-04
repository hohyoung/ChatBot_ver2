import React from 'react';
import './FilterPanel.css';

/**
 * FilterPanel - 문서 검색 필터 사이드바
 *
 * @param {Object} filters - 현재 필터 값
 * @param {Function} onChange - 필터 변경 콜백
 * @param {Function} onReset - 필터 초기화 콜백
 * @param {Object} stats - 문서 통계 (선택)
 */
export default function FilterPanel({ filters, onChange, onReset, stats }) {
  const handleInputChange = (key, value) => {
    onChange({ ...filters, [key]: value });
  };

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => currentYear - i);

  return (
    <div className="filter-panel">
      <div className="filter-panel-header">
        <h3>필터</h3>
        <button
          className="filter-panel-reset"
          onClick={onReset}
          title="필터 초기화"
        >
          초기화
        </button>
      </div>

      <div className="filter-panel-section">
        <label className="filter-panel-label">키워드</label>
        <input
          type="text"
          className="filter-panel-input"
          placeholder="문서 제목 검색..."
          value={filters.keyword || ''}
          onChange={(e) => handleInputChange('keyword', e.target.value)}
        />
      </div>

      <div className="filter-panel-section">
        <label className="filter-panel-label">태그</label>
        <input
          type="text"
          className="filter-panel-input"
          placeholder="태그 (콤마 구분)"
          value={filters.tags || ''}
          onChange={(e) => handleInputChange('tags', e.target.value)}
        />
        <small className="filter-panel-hint">
          예: hr-policy, vacation
        </small>
      </div>

      <div className="filter-panel-section">
        <label className="filter-panel-label">문서 유형</label>
        <select
          className="filter-panel-select"
          value={filters.doc_type || ''}
          onChange={(e) => handleInputChange('doc_type', e.target.value)}
        >
          <option value="">전체</option>
          {stats?.by_type && Object.keys(stats.by_type).map((type) => (
            <option key={type} value={type}>
              {type} ({stats.by_type[type]})
            </option>
          ))}
        </select>
      </div>

      <div className="filter-panel-section">
        <label className="filter-panel-label">공개 범위</label>
        <select
          className="filter-panel-select"
          value={filters.visibility || ''}
          onChange={(e) => handleInputChange('visibility', e.target.value)}
        >
          <option value="">전체</option>
          <option value="public">공개</option>
          <option value="org">조직</option>
          <option value="private">비공개</option>
        </select>
      </div>

      <div className="filter-panel-section">
        <label className="filter-panel-label">업로더</label>
        <input
          type="text"
          className="filter-panel-input"
          placeholder="업로더 이름"
          value={filters.owner_username || ''}
          onChange={(e) => handleInputChange('owner_username', e.target.value)}
        />
      </div>

      <div className="filter-panel-section">
        <label className="filter-panel-label">업로드 연도</label>
        <select
          className="filter-panel-select"
          value={filters.year || ''}
          onChange={(e) => handleInputChange('year', e.target.value ? parseInt(e.target.value) : null)}
        >
          <option value="">전체</option>
          {years.map((year) => (
            <option key={year} value={year}>
              {year}
            </option>
          ))}
        </select>
      </div>

      {stats && (
        <div className="filter-panel-stats">
          <h4>통계</h4>
          <div className="filter-panel-stat-item">
            <span>전체 문서:</span>
            <strong>{stats.total_docs || 0}</strong>
          </div>
          <div className="filter-panel-stat-item">
            <span>전체 청크:</span>
            <strong>{stats.total_chunks || 0}</strong>
          </div>
          {stats.recent_uploads > 0 && (
            <div className="filter-panel-stat-item">
              <span>최근 7일:</span>
              <strong>{stats.recent_uploads}</strong>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
