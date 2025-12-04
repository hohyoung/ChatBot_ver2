import React, { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import './MarkdownRenderer.css';

/**
 * 마크다운 렌더링 컴포넌트
 * - XSS 방지 (react-markdown 내장)
 * - 조항 하이라이트 (제\d+조)
 * - GFM 지원 (테이블, 취소선 등)
 * - 스트리밍 지원 (isStreaming=true일 때 실시간 렌더링)
 * - 이미지 확대 모달 지원
 * - 이미지 참조 변환: ![설명][IMG1] → 실제 이미지 URL로 변환
 *
 * @param {string} content - 마크다운 콘텐츠
 * @param {boolean} isStreaming - 스트리밍 중 여부
 * @param {Array} imageRefs - 이미지 참조 매핑 [{ref: "[IMG1]", url: "/static/images/..."}, ...]
 */
export default function MarkdownRenderer({ content, isStreaming = false, imageRefs = [] }) {
    const [imageModalSrc, setImageModalSrc] = useState(null);
    // react-markdown은 기본적으로 안전한 렌더링을 제공하므로
    // 별도의 sanitize 처리가 필요 없습니다.

    // 이미지 참조 ([IMG1], [IMG2] 등)를 실제 URL로 변환
    const processedContent = useMemo(() => {
        if (!content || !imageRefs || imageRefs.length === 0) {
            return content;
        }

        let result = content;

        // 이미지 참조 매핑 생성 (ref → url)
        const refToUrl = {};
        imageRefs.forEach((img) => {
            if (img.ref && img.url) {
                refToUrl[img.ref] = img.url;
            }
        });

        // 패턴 1: ![설명][IMG1] 형식 → ![설명](url) 형식으로 변환
        // 마크다운 참조 스타일 이미지 링크
        result = result.replace(/!\[([^\]]*)\]\[IMG(\d+)\]/gi, (match, alt, num) => {
            const ref = `[IMG${num}]`;
            const url = refToUrl[ref];
            if (url) {
                return `![${alt}](${url})`;
            }
            return match; // 매칭되는 URL 없으면 원본 유지
        });

        // 패턴 2: ![설명](IMG1) 형식 (LLM이 괄호 안에 넣는 경우)
        result = result.replace(/!\[([^\]]*)\]\(IMG(\d+)\)/gi, (match, alt, num) => {
            const ref = `[IMG${num}]`;
            const url = refToUrl[ref];
            if (url) {
                return `![${alt}](${url})`;
            }
            return match;
        });

        // 패턴 3: [IMG1] 단독 사용 (LLM이 참조만 남긴 경우)
        result = result.replace(/\[IMG(\d+)\]/gi, (match, num) => {
            const ref = `[IMG${num}]`;
            const url = refToUrl[ref];
            if (url) {
                return `![이미지 ${num}](${url})`;
            }
            return match;
        });

        return result;
    }, [content, imageRefs]);

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
        },
        // 이미지: 클릭하면 확대 모달
        img: ({ src, alt, ...props }) => {
            // /static/images/ 경로의 이미지만 확대 가능
            const isExpandable = src && src.startsWith('/static/images/');
            return (
                <span className="markdown-image-wrapper">
                    <img
                        src={src}
                        alt={alt || '이미지'}
                        className={`markdown-image ${isExpandable ? 'expandable' : ''}`}
                        onClick={isExpandable ? () => setImageModalSrc(src) : undefined}
                        {...props}
                    />
                    {alt && <span className="markdown-image-caption">{alt}</span>}
                </span>
            );
        }
    };

    return (
        <>
            <div className={`markdown-renderer ${isStreaming ? 'is-streaming' : ''}`}>
                <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={components}
                >
                    {processedContent}
                </ReactMarkdown>
                {isStreaming && <span className="streaming-cursor">▊</span>}
            </div>

            {/* 이미지 확대 모달 */}
            {imageModalSrc && (
                <div
                    className="markdown-image-modal-overlay"
                    onClick={() => setImageModalSrc(null)}
                >
                    <div className="markdown-image-modal-content" onClick={(e) => e.stopPropagation()}>
                        <button
                            className="markdown-image-modal-close"
                            onClick={() => setImageModalSrc(null)}
                            aria-label="닫기"
                        >
                            ×
                        </button>
                        <img
                            src={imageModalSrc}
                            alt="확대된 이미지"
                            className="markdown-image-modal-img"
                        />
                        <div className="markdown-image-modal-hint">클릭하여 닫기</div>
                    </div>
                </div>
            )}
        </>
    );
}
