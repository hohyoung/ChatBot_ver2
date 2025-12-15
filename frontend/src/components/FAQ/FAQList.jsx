// frontend/src/components/FAQ/FAQList.jsx
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import FAQCard from './FAQCard';
import LoadingSpinner from '../LoadingSpinner/LoadingSpinner';
import './FAQList.css';

// 표시할 최대 FAQ 개수
const MAX_FAQ_DISPLAY = 7;

/**
 * FAQ 리스트 컴포넌트
 *
 * FAQ 목록을 API에서 가져와 표시합니다. (상위 7개만 표시)
 */
const FAQList = ({ onQuestionClick, isInPanel = false }) => {
  const [faqList, setFaqList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchFAQ();
  }, []);

  const fetchFAQ = async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch('/api/faq/');

      if (!response.ok) {
        throw new Error('FAQ 로드 실패');
      }

      const data = await response.json();
      setFaqList(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleQuestionClick = (question) => {
    if (onQuestionClick) {
      onQuestionClick(question);
    }
  };

  // FAQ가 없으면 표시하지 않음
  if (!loading && faqList.length === 0) {
    return (
      <div className="faq-empty">
        등록된 FAQ가 없습니다.
      </div>
    );
  }

  // 패널 내부에서 사용될 때 (헤더 없이 리스트만)
  if (isInPanel) {
    return (
      <div className="faq-list-panel">
        {loading && (
          <div className="faq-loading">
            <LoadingSpinner size="sm" message="FAQ 불러오는 중..." />
          </div>
        )}

        {error && (
          <div className="faq-error">
            {error}
            <button onClick={fetchFAQ} className="faq-retry-btn">
              다시 시도
            </button>
          </div>
        )}

        {!loading && !error && faqList.length > 0 && (
          <div className="faq-cards">
            {faqList.slice(0, MAX_FAQ_DISPLAY).map((faq, index) => (
              <FAQCard
                key={index}
                question={faq.question}
                count={faq.count}
                onClick={handleQuestionClick}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  // 기존 독립 컴포넌트 형태 (하위 호환)
  const displayList = faqList.slice(0, MAX_FAQ_DISPLAY);

  return (
    <div className="faq-list-container">
      <div className="faq-list-header">
        <h3 className="faq-list-title">
          자주 묻는 질문
          {displayList.length > 0 && (
            <span className="faq-count-badge">{displayList.length}</span>
          )}
        </h3>
      </div>

      <div className="faq-list-content">
        {loading && (
          <div className="faq-loading">
            <LoadingSpinner size="sm" message="FAQ 불러오는 중..." />
          </div>
        )}

        {error && (
          <div className="faq-error">
            {error}
            <button onClick={fetchFAQ} className="faq-retry-btn">
              다시 시도
            </button>
          </div>
        )}

        {!loading && !error && displayList.length > 0 && (
          <div className="faq-cards">
            {displayList.map((faq, index) => (
              <FAQCard
                key={index}
                question={faq.question}
                count={faq.count}
                onClick={handleQuestionClick}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

FAQList.propTypes = {
  onQuestionClick: PropTypes.func.isRequired,
  isInPanel: PropTypes.bool,
};

export default FAQList;
