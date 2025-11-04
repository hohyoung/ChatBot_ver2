// frontend/src/components/FAQ/FAQList.jsx
import React, { useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import FAQCard from './FAQCard';
import './FAQList.css';

/**
 * FAQ 리스트 컴포넌트
 *
 * FAQ 목록을 API에서 가져와 표시합니다.
 */
const FAQList = ({ onQuestionClick }) => {
  const [faqList, setFaqList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [collapsed, setCollapsed] = useState(false);

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
      console.error('FAQ 로드 에러:', err);
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
    return null;
  }

  return (
    <div className="faq-list-container">
      <div className="faq-list-header">
        <h3 className="faq-list-title">
          자주 묻는 질문
          {faqList.length > 0 && (
            <span className="faq-count-badge">{faqList.length}</span>
          )}
        </h3>
        <button
          className="faq-toggle-btn"
          onClick={() => setCollapsed(!collapsed)}
          aria-label={collapsed ? 'FAQ 펼치기' : 'FAQ 접기'}
        >
          {collapsed ? '▼' : '▲'}
        </button>
      </div>

      {!collapsed && (
        <div className="faq-list-content">
          {loading && (
            <div className="faq-loading">FAQ를 불러오는 중...</div>
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
              {faqList.map((faq, index) => (
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
      )}
    </div>
  );
};

FAQList.propTypes = {
  onQuestionClick: PropTypes.func.isRequired,
};

export default FAQList;
