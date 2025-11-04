// frontend/src/components/FAQ/FAQCard.jsx
import React from 'react';
import PropTypes from 'prop-types';
import './FAQCard.css';

/**
 * FAQ 카드 컴포넌트
 *
 * 자주 묻는 질문을 표시하고, 클릭 시 질문을 입력창에 자동 입력합니다.
 */
const FAQCard = ({ question, count, onClick }) => {
  return (
    <div
      className="faq-card"
      onClick={() => onClick(question)}
      role="button"
      tabIndex={0}
      onKeyPress={(e) => {
        if (e.key === 'Enter') onClick(question);
      }}
    >
      <div className="faq-card-content">
        <div className="faq-question">{question}</div>
        {count > 0 && (
          <div className="faq-count" title={`${count}명이 질문했습니다`}>
            {count}
          </div>
        )}
      </div>
    </div>
  );
};

FAQCard.propTypes = {
  question: PropTypes.string.isRequired,
  count: PropTypes.number,
  onClick: PropTypes.func.isRequired,
};

FAQCard.defaultProps = {
  count: 0,
};

export default FAQCard;
