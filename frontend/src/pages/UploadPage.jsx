import React, { useEffect, useRef, useState } from "react";
import "./UploadPage.css";
import { post, get } from "../api/http.js";
import { me as fetchMe } from "../store/auth.js";

export default function UploadPage() {
    const [files, setFiles] = useState([]);
    const [job, setJob] = useState(null); // { job_id, accepted, skipped }
    const [status, setStatus] = useState(null); // { status, processed, total?, errors? }
    const [user, setUser] = useState(null); // { id, username, security_level, ... }
    const [errorMsg, setErrorMsg] = useState(""); // 화면에 띄울 에러 메시지
    const timerRef = useRef(null);

    const isLoggedIn = !!user;
    const isDenied = isLoggedIn && Number(user?.security_level) === 4; // 4등급: 업로드 불가
    const disabled = !isLoggedIn || isDenied;

    useEffect(() => {
        (async () => {
            try {
                const u = await fetchMe();
                setUser(u);
            } catch {
                setUser(null);
            }
        })();
        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, []);

    const onPick = (e) => setFiles(Array.from(e.target.files || []));
    const onDrop = (e) => {
        e.preventDefault();
        setFiles(Array.from(e.dataTransfer.files || []));
    };
    const onDrag = (e) => e.preventDefault();

    // 업로드 실행
    const upload = async () => {
        setErrorMsg("");

        if (!isLoggedIn) {
            setErrorMsg("로그인이 필요합니다. 상단의 로그인 버튼을 눌러 로그인해 주세요.");
            return;
        }
        if (isDenied) {
            setErrorMsg("보안등급 4(외부 계정)는 문서 업로드 권한이 없습니다.");
            return;
        }
        if (!files.length) {
            setErrorMsg("업로드할 파일을 선택하세요.");
            return;
        }

        const form = new FormData();
        for (const f of files) form.append("files", f, f.name);
        form.append("visibility", "public");

        try {
            const res = await post("/docs/upload", form); // { job_id, accepted, skipped }
            setJob(res);

            if (timerRef.current) clearInterval(timerRef.current);
            timerRef.current = setInterval(async () => {
                try {
                    const st = await get(`/docs/${res.job_id}/status`);
                    setStatus(st);
                    if (st?.status === "done" || st?.status === "error") {
                        clearInterval(timerRef.current);
                        timerRef.current = null;
                    }
                } catch (e) {
                    console.warn("status poll error", e?.message || e);
                }
            }, 1500);
        } catch (e) {
            let msg = e?.message || "업로드 중 오류가 발생했습니다.";
            try {
                const obj = JSON.parse(msg);
                if (obj?.detail) msg = obj.detail;
            } catch (_) { }
            setErrorMsg(msg);
        }
    };

    return (
        <div className="upload-page">
            <h2>문서 업로드</h2>

            {!isLoggedIn && (
                <div className="banner warning">
                    로그인한 사용자만 문서를 업로드할 수 있습니다. 상단의 <b>로그인</b> 버튼을 눌러 로그인해 주세요.
                </div>
            )}
            {isDenied && (
                <div className="banner error">
                    <b>업로드 권한 없음</b> — 보안등급 4(외부 계정)는 문서 업로드가 제한됩니다.
                </div>
            )}
            {errorMsg && <div className="banner error">{errorMsg}</div>}

            <div className="section">
                <h3 style={{ marginTop: 0 }}>파일 선택</h3>
                <div className={`card ${disabled ? "is-disabled" : ""}`}>
                    <div style={{ marginBottom: 8 }}>
                        <input type="file" multiple onChange={onPick} />
                    </div>

                    <div
                        className={`dropzone ${disabled ? "is-disabled" : ""}`}
                        onDrop={onDrop}
                        onDragOver={onDrag}
                    >
                        여기로 파일을 끌어다 놓거나, 위에서 선택하세요.
                    </div>

                    <div style={{ marginTop: 10, display: "flex", gap: 8, justifyContent: "flex-end" }}>
                        <button className="btn btn-primary" onClick={upload} disabled={disabled}>
                            업로드
                        </button>
                    </div>

                    <div className="small">여러 파일 선택 가능. 업로드 후 인덱싱 상태를 폴링합니다.</div>
                </div>
            </div>

            <div className="section">
                <h3 style={{ marginTop: 0 }}>상태</h3>
                <div className="card">
                    <div className="status-grid">
                        <div className="key">선택 파일</div>
                        <div className="val">{files.length}</div>

                        <div className="key">잡</div>
                        <div className="val">{job ? JSON.stringify(job) : "—"}</div>

                        <div className="key">진행</div>
                        <div className="val">{status ? JSON.stringify(status) : "—"}</div>
                    </div>
                </div>
            </div>
        </div>
    );
}
