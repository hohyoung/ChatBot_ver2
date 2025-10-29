import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import DOMPurify from 'dompurify';
import './MarkdownRenderer.css';

/**
 * 마크다운 렌더링 컴포넌트
 * - XSS 방지 (DOMPurify)
 * - 조항 하이라이트 (제\d+조)
 * - GFM 지원 (테이블, 취소선 등)
 */
export default function MarkdownRenderer({ content }) {
    // XSS 방지: DOMPurify로 정제
    const sanitizedContent = useMemo(() => {
        return DOMPurify.sanitize(content, {
            ALLOWED_TAGS: [
                'p', 'br', 'strong', 'em', 'u', 'code', 'pre',
                'ul', 'ol', 'li', 'blockquote',
                'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'table', 'thead', 'tbody', 'tr', 'th', 'td',
                'a', 'span'
            ],
            ALLOWED_ATTR: ['href', 'class', 'id', 'target', 'rel']
        });
    }, [content]);

    // 조항 하이라이트 처리 (제\d+조, 제\d+항)
    const highlightLegalClauses = (text) => {
        // 정규식: 제10조, 제2항 등
        const clauseRegex = /(제\d+조|제\d+항)/g;
        const parts = text.split(clauseRegex);

        return parts.map((part, index) => {
            if (clauseRegex.test(part)) {
                return <span key={index} className="legal-clause-highlight">{part}</span>;
            }
            return part;
        });
    };

    // 커스텀 렌더러: 텍스트 노드에 조항 하이라이트 적용
    const components = {
        p: ({ children, ...props }) => {
            // children이 문자열이면 하이라이트 처리
            const processedChildren = React.Children.map(children, (child) => {
                if (typeof child === 'string') {
                    return highlightLegalClauses(child);
                }
                return child;
            });
            return <p {...props}>{processedChildren}</p>;
        },
        li: ({ children, ...props }) => {
            const processedChildren = React.Children.map(children, (child) => {
                if (typeof child === 'string') {
                    return highlightLegalClauses(child);
                }
                return child;
            });
            return <li {...props}>{processedChildren}</li>;
        },
        // 코드 블록 스타일
        code: ({ inline, className, children, ...props }) => {
            return inline ? (
                <code className="inline-code" {...props}>{children}</code>
            ) : (
                <pre className="code-block">
                    <code className={className} {...props}>{children}</code>
                </pre>
            );
        },
        // 링크는 새 탭에서 열기
        a: ({ href, children, ...props }) => {
            return (
                <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                    {children}
                </a>
            );
        },
        // 테이블 스타일
        table: ({ children, ...props }) => {
            return (
                <div className="table-wrapper">
                    <table className="markdown-table" {...props}>{children}</table>
                </div>
            );
        }
    };

    return (
        <div className="markdown-renderer">
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={components}
            >
                {sanitizedContent}
            </ReactMarkdown>
        </div>
    );
}
