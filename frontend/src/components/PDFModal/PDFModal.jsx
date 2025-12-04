import React from 'react';
import './PDFModal.css';
import { STATIC_BASE } from '../../api/http.js';

function buildDocUrl(meta) {
    if (!meta) return null;

    const relRaw = String(meta.doc_relpath || "");
    const relNorm = relRaw.replace(/\\/g, "/").replace(/^\/+/, "");

    let relCore = relNorm;
    for (const p of ["public/", "static/docs/"]) {
        if (relCore.startsWith(p)) relCore = relCore.slice(p.length);
    }

    let url = meta.doc_url || (relCore ? `/static/docs/${relCore}` : null);
    if (url) {
        url = url.replace("/static/docs/public/", "/static/docs/");
        url = url.replace("/static/docs/static/docs/", "/static/docs/");
    }

    const page = Number(meta.page_start);
    const anchor =
        url && url.toLowerCase().endsWith(".pdf") && Number.isFinite(page) && page > 0
            ? `#page=${page}`
            : "";

    return url ? (url.startsWith("/") ? STATIC_BASE + url : url) + anchor : null;
}

function isPdfUrl(url) {
    return url && url.toLowerCase().includes(".pdf");
}

export default function PDFModal({ source, onClose }) {
    if (!source) return null;

    const finalUrl = buildDocUrl(source);
    const isPdf = isPdfUrl(finalUrl);
    const title = source.doc_title || source.doc_id || "문서";

    return (
        <div className="pdf-modal-overlay" onClick={onClose}>
            <div className="pdf-modal-container" onClick={(e) => e.stopPropagation()}>
                <div className="pdf-modal-header">
                    <div className="pdf-modal-title">
                        <span className="pdf-icon">📄</span>
                        {title}
                        {source.page_start && (
                            <span className="pdf-page-badge">p.{source.page_start}</span>
                        )}
                    </div>
                    <div className="pdf-modal-actions">
                        {finalUrl && (
                            <a
                                href={finalUrl}
                                target="_blank"
                                rel="noreferrer"
                                className="pdf-open-btn"
                            >
                                새 탭으로 열기
                            </a>
                        )}
                        <button className="pdf-close-btn" onClick={onClose}>
                            ✕
                        </button>
                    </div>
                </div>

                <div className="pdf-modal-body">
                    {finalUrl ? (
                        isPdf ? (
                            <iframe
                                key={finalUrl}
                                src={finalUrl}
                                title={title}
                                className="pdf-viewer-iframe"
                            />
                        ) : (
                            <div className="pdf-modal-empty">
                                이 형식은 미리보기가 어렵습니다.{" "}
                                <a href={finalUrl} target="_blank" rel="noreferrer">
                                    새 탭으로 열기
                                </a>
                            </div>
                        )
                    ) : (
                        <div className="pdf-modal-empty">
                            문서를 불러올 수 없습니다.
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
