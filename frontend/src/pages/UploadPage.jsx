import React, { useEffect, useRef, useState } from "react";
import "./UploadPage.css";
import { get, getAuthToken, docsApi } from "../api/http.js";
import { me as fetchMe } from "../store/auth.js";
import {
    FaFileUpload,
    FaCheckCircle,
    FaExclamationCircle,
    FaSpinner,
    FaFileAlt,
    FaTrash,
    FaLock,
    FaInfoCircle
} from "react-icons/fa";

/* 상태 표시 */
const StatusDisplay = ({ status, job }) => {
    if (!status && !job) {
        return (
            <div className="status-item info">
                <div className="status-icon"><FaFileAlt /></div>
                <div className="status-content">
                    <h4>대기 중</h4>
                    <p>업로드할 파일을 선택한 뒤 업로드를 시작하세요.</p>
                </div>
            </div>
        );
    }
    if (job && !status) {
        return (
            <div className="status-item info">
                <div className="status-icon"><FaSpinner className="fa-spin" /></div>
                <div className="status-content">
                    <h4>업로드 접수됨</h4>
                    <p>{job.accepted}개의 파일이 대기열에 추가되었습니다. 잠시 후 인덱싱이 시작됩니다.</p>
                </div>
            </div>
        );
    }
    if (status?.status === "pending") {
        return (
            <div className="status-item info">
                <div className="status-icon"><FaSpinner className="fa-spin" /></div>
                <div className="status-content">
                    <h4>대기 중</h4>
                    <p>작업이 곧 시작됩니다. 잠시만 기다려주세요.</p>
                </div>
            </div>
        );
    }
    if (status?.status === "running") {
        return (
            <div className="status-item processing">
                <div className="status-icon"><FaSpinner className="fa-spin" /></div>
                <div className="status-content">
                    <h4>인덱싱 작업 중…</h4>
                    <p>총 {status.total ?? "-"}개 중 {status.processed ?? 0}개 처리 완료</p>
                </div>
            </div>
        );
    }
    if (status?.status === "succeeded") {
        return (
            <div className="status-item success">
                <div className="status-icon"><FaCheckCircle /></div>
                <div className="status-content">
                    <h4>업로드 성공</h4>
                    <p>모든 파일의 인덱싱이 완료되었습니다.</p>
                </div>
            </div>
        );
    }
    if (status?.status === "failed") {
        return (
            <div className="status-item error">
                <div className="status-icon"><FaExclamationCircle /></div>
                <div className="status-content">
                    <h4>업로드 실패</h4>
                    <p>{status.message || "처리 중 오류가 발생했습니다."}</p>
                </div>
            </div>
        );
    }
    return null;
};

export default function UploadPage() {
    const [files, setFiles] = useState([]);
    const [job, setJob] = useState(null);
    const [status, setStatus] = useState(null);
    const [user, setUser] = useState(null);
    const [errorMsg, setErrorMsg] = useState("");
    const [isDragOver, setIsDragOver] = useState(false);
    const timerRef = useRef(null);
    const fileInputRef = useRef(null);

    const isLoggedIn = !!user;
    // ✅ 업로드 허용 등급: 1~3 허용, 4(차단)는 불가
    const canUploadByLevel = isLoggedIn && Number(user?.security_level) <= 3;
    const isUploading = status?.status === "running" || status?.status === "pending" || (job && !status);
    const disabled = !canUploadByLevel || isUploading; // 비로그인 or 4등급 or 업로딩 중

    useEffect(() => {
        (async () => {
            try { setUser(await fetchMe()); } catch { setUser(null); }
        })();

        // ⬇ 로그인/로그아웃 시 페이지 새로고침
        const onAuthChanged = () => window.location.reload();
        const onStorage = (e) => {
            if (e.key === "auth_token") onAuthChanged();
        };
        window.addEventListener("auth:changed", onAuthChanged);
        window.addEventListener("storage", onStorage);

        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
            window.removeEventListener("auth:changed", onAuthChanged);
            window.removeEventListener("storage", onStorage);
        };
    }, []);

    const pollStatus = (job_id) => {
        if (timerRef.current) clearInterval(timerRef.current);
        timerRef.current = setInterval(async () => {
            try {
                const stat = await get(`/docs/${encodeURIComponent(job_id)}/status`);
                setStatus(stat);
                if (stat.status === "succeeded" || stat.status === "failed") {
                    clearInterval(timerRef.current);
                    timerRef.current = null;
                    setFiles([]); // 완료 후 비우기
                }
            } catch {
                setErrorMsg("상태를 가져오는 데 실패했습니다.");
                clearInterval(timerRef.current);
                timerRef.current = null;
            }
        }, 1500);
    };

    const upload = async () => {
        if (!canUploadByLevel) return;
        if (files.length === 0) {
            setErrorMsg("업로드할 파일을 선택해주세요.");
            return;
        }
        setJob(null); setStatus(null); setErrorMsg("");

        const formData = new FormData();
        files.forEach((f) => formData.append("files", f));
        formData.append("visibility", "public");

        try {
            // 💡 복잡한 fetch 로직이 이 한 줄로 깔끔하게 정리됩니다.
            const result = await docsApi.upload(formData);

            setJob(result);
            if (result?.job_id) pollStatus(result.job_id);
        } catch (err) {
            console.error("Upload failed:", err);
            setErrorMsg(err?.message || "파일 업로드에 실패했습니다.");
        }
    };

    const addFiles = (newFiles) => {
        if (!canUploadByLevel) return; // 안전장치
        setFiles((prev) => {
            const combined = [...prev, ...newFiles];
            return Array.from(new Map(combined.map((f) => [f.name, f])).values());
        });
    };

    const onPick = (e) => {
        if (!canUploadByLevel) return;
        const picked = Array.from(e.target.files || []);
        addFiles(picked);
        if (fileInputRef.current) fileInputRef.current.value = "";
    };

    const handleDragOver = (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!canUploadByLevel) return;
        setIsDragOver(true);
    };
    const handleDragLeave = (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!canUploadByLevel) return;
        setIsDragOver(false);
    };
    const handleDrop = (e) => {
        e.preventDefault(); e.stopPropagation();
        if (!canUploadByLevel) return;
        setIsDragOver(false);
        const dropped = Array.from(e.dataTransfer.files || []);
        if (dropped.length > 0) addFiles(dropped);
    };

    const removeFile = (name) => setFiles((fs) => fs.filter((f) => f.name !== name));

    const showLoginGuard = !isLoggedIn;
    const showLevelGuard = isLoggedIn && !canUploadByLevel; // (= 4등급)

    return (
        <div className="upload-page">
            <h2>문서 업로드</h2>


            <div className="info-banner">
                <FaInfoCircle />
                <p>
                    <strong>PDF 형식의 파일을 권장합니다.</strong>
                    <br />
                    PDF로 업로드 시, 문서 미리보기가 가능해 품질 좋은 답변을 얻을 수 있습니다.
                </p>
            </div>

            {/* 🔒 가드 배너 */}
            {showLoginGuard && (
                <div className="guard-banner">
                    <FaLock />
                    <div>
                        <strong>로그인이 필요합니다.</strong>
                        <div>로그인 후 업로드 기능을 이용할 수 있어요.</div>
                    </div>
                </div>
            )}
            {showLevelGuard && (
                <div className="guard-banner">
                    <FaLock />
                    <div>
                        <strong>권한이 부족합니다.</strong>
                        <div>보안등급 1–3 사용자만 업로드할 수 있어요.</div>
                    </div>
                </div>
            )}

            {/* 드랍존 카드 */}
            <div className="section">
                <div className={`card dropzone-card ${disabled ? "is-disabled" : ""}`}>
                    {/* 잠금 오버레이 */}
                    {disabled && (
                        <div className="blocked-overlay">
                            <FaLock />
                            <div className="blocked-text">
                                {showLoginGuard ? "로그인 후 이용 가능합니다" : "업로드 권한이 없습니다"}
                            </div>
                        </div>
                    )}

                    <label className="file-input-label">
                        <input
                            ref={fileInputRef}
                            type="file"
                            multiple
                            onChange={onPick}
                            disabled={disabled}
                            accept=".pdf,.docx,.txt,.html,.md,.csv,.pptx"
                        />
                        📂 파일 추가
                    </label>

                    <div
                        className={`dropzone ${isDragOver ? "is-dragover" : ""} ${disabled ? "is-blocked" : ""}`}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onDrop={handleDrop}
                    >
                        {files.length === 0 ? (
                            <div className="dropzone-placeholder">
                                <FaFileUpload />
                                <p>여기로 파일을 끌어다 놓으세요.</p>
                            </div>
                        ) : (
                            <div className="file-list">
                                {files.map((f) => (
                                    <div key={f.name} className="file-item">
                                        <span className="file-name">{f.name}</span>
                                        <button className="remove-btn" onClick={() => removeFile(f.name)} disabled={isUploading}>
                                            <FaTrash />
                                        </button>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="button-area">
                        <button className="btn btn-primary" onClick={upload} disabled={disabled || files.length === 0}>
                            {isUploading ? "처리 중..." : `파일 ${files.length}개 업로드`}
                        </button>
                    </div>
                </div>
            </div>

            {/* 상태 카드 */}
            <div className="section status-section">
                <h3>업로드 상태</h3>
                <div className="card">
                    <div className="status-box">
                        <StatusDisplay status={status} job={job} />
                    </div>
                </div>
            </div>

            {/* 서버/클라이언트 오류 배너 */}
            {errorMsg && <div className="error-banner">{errorMsg}</div>}
        </div>
    );
}
