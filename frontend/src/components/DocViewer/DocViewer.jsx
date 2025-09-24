// src/components/DocViewer/DocViewer.jsx
import React, { useEffect, useMemo, useState } from "react";
import "./DocViewer.css";

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

    return url ? url + anchor : null;
}

function isPdfUrl(url) {
    return url && url.toLowerCase().includes(".pdf");
}

export default function DocViewer({ source }) {
    const [finalUrl, setFinalUrl] = useState(null);

    const title = useMemo(() => {
        return source ? (source.doc_title || source.doc_id || "문서") : "문서 미리보기";
    }, [source]);

    useEffect(() => {
        if (!source) {
            setFinalUrl(null);
            return;
        }
        const url = buildDocUrl(source);
        setFinalUrl(url || null);
    }, [source]);

    const isPdf = isPdfUrl(finalUrl);

    return (
        <div className="viewer">
            <div className="viewer__header">
                <div className="viewer__title">{title}</div>
                {finalUrl && (
                    <a href={finalUrl} target="_blank" rel="noreferrer" className="viewer__open">
                        새 탭으로 열기
                    </a>
                )}
            </div>

            <div className="viewer__body">
                {finalUrl ? (
                    isPdf ? (
                        // ★★★ 핵심 수정: iframe에 key={finalUrl} 속성 추가 ★★★
                        <iframe key={finalUrl} src={finalUrl} title={title} />
                    ) : (
                        <div className="viewer__empty">
                            이 형식은 미리보기가 어렵습니다.{" "}
                            <a href={finalUrl} target="_blank" rel="noreferrer">
                                새 탭으로 열기
                            </a>
                        </div>
                    )
                ) : (
                    <div className="viewer__empty">PDF 뷰어입니다. 답변의 근거 자료를 띄워줍니다. 다른 형식의 파일의 경우 링크를 띄웁니다.</div>
                )}
            </div>
        </div>
    );
}