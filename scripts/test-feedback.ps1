param(
  [string]$BaseUrl = "http://127.0.0.1:8000",
  [string]$Question,
  [string[]]$Tags
)

# --- 인코딩 고정 ---
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [System.Text.Encoding]::UTF8

function Invoke-ChatDebug([string]$q, [string[]]$tags) {
  $body = @{ question = $q } 
  if ($tags -and $tags.Count -gt 0) { $body.tags = $tags }
  $json = $body | ConvertTo-Json -Compress -Depth 5
  return Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/chat.debug" `
           -ContentType "application/json; charset=utf-8" -Body $json
}

function Send-Feedback([string]$chunkId, [string]$vote = "up") {
  $fb = @{ chunk_id = $chunkId; vote = $vote } | ConvertTo-Json -Compress
  return Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/feedback" `
           -ContentType "application/json; charset=utf-8" -Body $fb
}

Write-Host "== 1) 1차 질의 =="
$resp1 = Invoke-ChatDebug -q $Question -tags $Tags
$chunks1 = @($resp1.data.chunks)
if (-not $chunks1 -or $chunks1.Count -eq 0) {
  Write-Warning "후보(chunks)가 없습니다. 응답만 출력합니다."
  $resp1 | ConvertTo-Json -Depth 6
  exit 0
}
$top1 = $chunks1[0]
Write-Host ("Top1 before: {0} (doc={1})" -f $top1.chunk_id, $top1.doc_title)

Write-Host "== 2) Top1 업보트 =="
$fbResp = Send-Feedback -chunkId $top1.chunk_id -vote "up"
$fbResp | ConvertTo-Json -Depth 6

Write-Host "== 3) 동일 질의 재시도 =="
$resp2 = Invoke-ChatDebug -q $Question -tags $Tags
$chunks2 = @($resp2.data.chunks)
$top2 = $chunks2[0]
Write-Host ("Top1 after : {0} (doc={1})" -f $top2.chunk_id, $top2.doc_title)

# 단순 비교 표시
if ($top1.chunk_id -eq $top2.chunk_id) {
  Write-Host "✅ 업보트한 청크가 여전히 1위입니다 (부스트 반영 정상)."
} else {
  Write-Host "ℹ️ 업보트한 청크가 1위가 아닙니다. 전체 로그에서 factor/score를 확인하세요."
}
