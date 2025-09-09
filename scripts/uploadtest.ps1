param(
  [Parameter(Mandatory = $true)]
  [string]$FilePath,
  [string]$ApiBase = "http://127.0.0.1:8000",
  [string]$DocType = "hr-guideline",
  [string]$Visibility = "org"   # org | private | public
)

# Windows PowerShell(5.1)에서 한글/UTF-8 출력을 위해
if ($PSVersionTable.PSEdition -ne 'Core') {
  [Console]::InputEncoding  = [System.Text.Encoding]::UTF8
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
}

# 경로 확인(리터럴, 한글/공백 안전)
try {
  $item = Get-Item -LiteralPath $FilePath -ErrorAction Stop
} catch {
  Write-Error "파일이 존재하지 않습니다: $FilePath"
  exit 1
}
$full = $item.FullName
# curl용 슬래시(백슬래시→슬래시)
$fullCurl = $full -replace '\\','/'

# curl.exe 사용 확인
$curl = "curl.exe"
try { $null = & $curl --version 2>$null } catch {
  Write-Error "curl.exe 를 찾을 수 없습니다."
  exit 1
}

$uploadUrl = "$ApiBase/api/docs/upload"
$argsList = @(
  "-sS","-X","POST",
  "-F", "files=@$fullCurl;type=application/pdf",
  "-F", "doc_type=$DocType",
  "-F", "visibility=$Visibility",
  $uploadUrl
)

Write-Host "Uploading '$full' → $uploadUrl ..."
$resp = & $curl @argsList
if ($LASTEXITCODE -ne 0) {
  Write-Error "업로드 실패 (curl exit $LASTEXITCODE)"
  exit $LASTEXITCODE
}
$resp
Write-Host "`n완료! (업로드 응답이 위에 출력되었습니다.)"
