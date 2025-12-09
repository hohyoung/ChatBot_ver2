/**
 * 날짜 포맷 유틸리티
 *
 * 여러 컴포넌트에서 사용되는 날짜 포맷 함수를 통합합니다.
 */

/**
 * 날짜를 YYYY-MM-DD HH:mm 형식으로 변환
 * @param {string|Date|null} value - 변환할 날짜 값
 * @returns {string} 포맷된 날짜 문자열 또는 "-"
 */
export function formatDateTime(value) {
    if (!value) return "-";
    try {
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return "-";

        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");
        const hh = String(d.getHours()).padStart(2, "0");
        const mi = String(d.getMinutes()).padStart(2, "0");

        return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
    } catch {
        return "-";
    }
}

/**
 * 날짜를 YYYY-MM-DD 형식으로 변환
 * @param {string|Date|null} value - 변환할 날짜 값
 * @returns {string} 포맷된 날짜 문자열 또는 "-"
 */
export function formatDate(value) {
    if (!value) return "-";
    try {
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return "-";

        const yyyy = d.getFullYear();
        const mm = String(d.getMonth() + 1).padStart(2, "0");
        const dd = String(d.getDate()).padStart(2, "0");

        return `${yyyy}-${mm}-${dd}`;
    } catch {
        return "-";
    }
}

/**
 * 날짜를 한국 로케일 형식으로 변환 (예: 2025. 1. 15.)
 * @param {string|Date|null} value - 변환할 날짜 값
 * @returns {string} 포맷된 날짜 문자열 또는 빈 문자열
 */
export function formatDateKorean(value) {
    if (!value) return "";
    try {
        const d = new Date(value);
        if (Number.isNaN(d.getTime())) return "";
        return d.toLocaleDateString("ko-KR");
    } catch {
        return "";
    }
}

// 레거시 지원: 기존 fmtDate 호환
export const fmtDate = formatDateTime;
