import React, { useState } from 'react';
import './ChatPanel.css';

/**
 * URL 정규화 유틸
 * - \ → /, 선행 / 제거
 * - 'public/' / 'static/docs/' 접두어 제거 후 core 추출
 * - 서버가 내려준 doc_url 우선, 없으면 /static/docs/<core>
 * - 오래된 메타 보호: '/static/docs/public/' · '/static/docs/static/docs/' 중복 접두어 정리
 * - PDF면 #page=<page_start> 앵커 부착
 */
function buildDocUrl(meta) {
    if (!meta) return null;

    const relRaw = String(meta.doc_relpath || '');
    const relNorm = relRaw.replace(/\\/g, '/').replace(/^\/+/, '');

    let relCore = relNorm;
    for (const p of ['public/', 'static/docs/']) {
        if (relCore.startsWith(p)) relCore = relCore.slice(p.length);
    }

    let url = meta.doc_url || (relCore ? `/static/docs/${relCore}` : null);

    if (url) {
        url = url.replace('/static/docs/public/', '/static/docs/');
        url = url.replace('/static/docs/static/docs/', '/static/docs/');
    }

    const page = Number(meta.page_start);
    const anchor =
        url && url.toLowerCase().endsWith('.pdf') && Number.isFinite(page) && page > 0
            ? `#page=${page}`
            : '';

    return url ? url + anchor : null;
}

export default function ChatPanel({
    connecting = false,
    answer = '',
    sources = [],
    selectedIndex = null,
    onAsk,
    onSelectSource,
    onFeedback,
}) {
    const [q, setQ] = useState('');

    const send = () => {
        const t = q.trim();
        if (!t || connecting) return;
        onAsk?.(t);
    };

    const onKey = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            send();
        }
    };

    return (
        <div className="panel">
            {/* 좌측: 대화/입력 */}
            <section className="panel__left">
                <div className="ask">
                    <textarea
                        className="ask__input"
                        placeholder="무엇이든 물어보세요…"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        onKeyDown={onKey}
                        disabled={connecting}
                    />
                    <div className="ask__actions">
                        <button className="btn" disabled={connecting || !q.trim()} onClick={send}>
                            {connecting ? '생성 중…' : '질의'}
                        </button>
                    </div>
                </div>

                <div className="answer">
                    {answer ? (
                        <pre className="answer__text">{answer}</pre>
                    ) : (
                        <div className="answer__placeholder">답변이 여기에 표시됩니다.</div>
                    )}
                </div>
            </section>

            {/* 우측: 근거 카드 리스트 */}
            <section className="panel__right">
                <div className="sources">
                    <div className="sources__header">
                        <div className="title">근거 자료</div>
                        <div className="count">{sources?.length || 0}건</div>
                    </div>

                    <div className="sources__body">
                        {(!sources || sources.length === 0) && (
                            <div className="sources__empty">표시할 근거가 없습니다.</div>
                        )}

                        {sources?.map((s, i) => {
                            const href = buildDocUrl(s);
                            const active = i === selectedIndex;
                            return (
                                <div
                                    key={s.chunk_id || i}
                                    className={`source ${active ? 'source--active' : ''}`}
                                    onClick={() => onSelectSource?.(s, i)}
                                    role="button"
                                    tabIndex={0}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter' || e.key === ' ') onSelectSource?.(s, i);
                                    }}
                                >
                                    <div className="source__header">
                                        <div className="source__title">
                                            {s.doc_title || s.doc_id || '무제'}
                                        </div>
                                        <div className="source__meta">
                                            {/* 페이지 정보(있을 때만) */}
                                            {Number.isFinite(Number(s.page_start)) && (
                                                <span className="pill">p.{Number(s.page_start)}</span>
                                            )}
                                            {/* 상태 pill: 링크 유무 안내 */}
                                            {href ? (
                                                <span className="pill pill--ok">링크 사용 가능</span>
                                            ) : (
                                                <span className="pill pill--muted">링크 없음</span>
                                            )}
                                        </div>
                                    </div>

                                    {/* 일부 내용 스니펫 */}
                                    <div className="source__snippet">
                                        {(s.focus_sentence || s.content || '').slice(0, 220)}
                                        {(s.focus_sentence || s.content || '').length > 220 ? '…' : ''}
                                    </div>

                                    <div className="source__footer">
                                        <div className="source__path">
                                            {/* 사용자에게 보일 경로 텍스트 (실제 링크는 actions에서 제공) */}
                                            {s.doc_relpath || s.doc_url || ''}
                                        </div>

                                        <div className="source__actions">
                                            <button
                                                className="btn btn-ghost"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onFeedback?.(s.chunk_id, 'up');
                                                }}
                                            >
                                                👍 좋았어요
                                            </button>

                                            <button
                                                className="btn btn-ghost"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onFeedback?.(s.chunk_id, 'down');
                                                }}
                                            >
                                                👎 별로였어요
                                            </button>

                                            {/* 새 탭으로 문서 열기 (카드 선택과 클릭 이벤트 분리) */}
                                            {href && (
                                                <a
                                                    className="btn btn-ghost"
                                                    href={href}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    onClick={(e) => e.stopPropagation()}
                                                    title="문서를 새 탭으로 열기"
                                                >
                                                    🔗 문서 열기
                                                </a>
                                            )}
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>
        </div>
    );
}
