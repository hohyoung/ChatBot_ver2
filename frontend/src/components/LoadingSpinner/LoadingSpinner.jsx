import React from 'react';
import './LoadingSpinner.css';

/**
 * 공통 로딩 스피너 컴포넌트
 * @param {string} size - 'sm' | 'md' | 'lg' (기본: 'md')
 * @param {string} message - 로딩 메시지 (선택)
 * @param {boolean} inline - true면 인라인 표시 (버튼 내부 등)
 * @param {string} color - 스피너 색상 (기본: 'primary')
 */
export default function LoadingSpinner({
    size = 'md',
    message = '',
    inline = false,
    color = 'primary'
}) {
    const containerClass = inline
        ? 'loading-spinner-inline'
        : 'loading-spinner-container';

    return (
        <div className={`${containerClass} size-${size}`}>
            <div className={`loading-spinner color-${color}`}>
                <div className="spinner-ring"></div>
            </div>
            {message && <span className="loading-message">{message}</span>}
        </div>
    );
}

/**
 * 스켈레톤 로더 - 콘텐츠 자리 표시
 */
export function SkeletonLoader({ width = '100%', height = '1em', borderRadius = '4px' }) {
    return (
        <div
            className="skeleton-loader"
            style={{ width, height, borderRadius }}
        />
    );
}

/**
 * 전체 페이지 로딩 상태
 */
export function PageLoader({ message = '로딩 중...' }) {
    return (
        <div className="page-loader">
            <LoadingSpinner size="lg" message={message} />
        </div>
    );
}

/**
 * 카드 형태의 로딩 상태 (테이블 등 대체용)
 */
export function CardLoader({ message = '불러오는 중...', icon = null }) {
    return (
        <div className="card-loader">
            {icon && <div className="card-loader-icon">{icon}</div>}
            <LoadingSpinner size="md" />
            <span className="card-loader-message">{message}</span>
        </div>
    );
}
