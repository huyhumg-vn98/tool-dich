# ============================================================
#  CÀI ĐẶT TOOL DỊCH VIDEO DOUYIN -> TIẾNG VIỆT (Windows 10/11)
#  Chạy bằng cách bấm đúp CaiDat.bat. Lần đầu mất khoảng 15-30 phút.
# ============================================================
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"          # tải file nhanh hơn
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$GOC = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $GOC
$PVT_COMMIT = "370a65ca391022e32355413bd6be22156ade943c"   # bản pyVideoTrans đã kiểm tra
$FFMPEG_ZIP = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
$GIT_ZIP = "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/MinGit-2.47.1-64-bit.zip"

function Buoc($t) { Write-Host "`n==> $t" -ForegroundColor Green }

# Tải 1 file lớn bằng curl: mạng đứt thì TẢI TIẾP từ chỗ đứt (không tải lại từ đầu).
# Đóng cửa sổ / chạy lại CaiDat.bat cũng giữ phần đã tải (file .tam).
function TaiFile($url, $dich, $hash = "") {
    if (Test-Path $dich) { return }
    $tam = "$dich.tam"
    $ma = 1
    foreach ($lan in 1..30) {
        & curl.exe -fL --retry 10 --retry-delay 5 --retry-all-errors --connect-timeout 30 -C - -o $tam $url
        $ma = $LASTEXITCODE
        if ($ma -eq 0) { break }
        if ($ma -eq 33 -or $ma -eq 36) { Remove-Item $tam -ErrorAction SilentlyContinue }   # máy chủ không cho tải tiếp -> tải lại
        Write-Host "Mạng bị đứt - tự tải tiếp (lần $($lan + 1)/30), phần đã tải vẫn giữ..." -ForegroundColor Yellow
        Start-Sleep -Seconds 5
    }
    if ($ma -ne 0) { throw "Không tải được $url - mạng quá yếu. Chạy lại CaiDat.bat sẽ tải tiếp phần còn lại." }
    if ($hash -and ((Get-FileHash $tam -Algorithm SHA256).Hash.ToLower() -ne $hash)) {
        Remove-Item $tam -ErrorAction SilentlyContinue
        throw "File tải về bị hỏng ($dich). Chạy lại CaiDat.bat để tải lại."
    }
    Move-Item -Force $tam $dich
}

try {
    Write-Host "Thư mục cài: $GOC"

    # ---------- 1. uv (quản lý Python) ----------
    Buoc "1/6 Cài uv (công cụ cài Python)"
    $uvDir = "$env:USERPROFILE\.local\bin"
    $env:Path = "$uvDir;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$uvDir;$env:Path"
    }
    uv --version

    # ---------- Git (vài thư viện của pyVideoTrans phải tải bằng Git) ----------
    # Máy chưa có Git -> tải bản Git gọn (MinGit) vào thư mục tool, không cần quyền quản trị.
    # (Không bắt buộc: tải lỗi thì vẫn cài tiếp được.)
    try {
        if (Test-Path "$GOC\git\cmd\git.exe") { $env:Path = "$GOC\git\cmd;$env:Path" }
        if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
            Write-Host "Máy chưa có Git - đang tải bản Git gọn..."
            $zip = "$env:TEMP\dichvideo_git.zip"
            TaiFile $GIT_ZIP $zip
            if (Test-Path "$GOC\git") { Remove-Item "$GOC\git" -Recurse -Force }
            Expand-Archive $zip "$GOC\git" -Force
            Remove-Item $zip -Force -ErrorAction SilentlyContinue
            $env:Path = "$GOC\git\cmd;$env:Path"
        }
        git --version
    } catch {
        Write-Host "Không tải được Git - bỏ qua (không bắt buộc)." -ForegroundColor Yellow
    }

    # ---------- 2. ffmpeg ----------
    Buoc "2/6 Tải ffmpeg (xử lý video)"
    if (-not (Test-Path "$GOC\ffmpeg\bin\ffmpeg.exe")) {
        $zip = "$env:TEMP\dichvideo_ffmpeg.zip"
        $tam = "$env:TEMP\dichvideo_ffmpeg"
        TaiFile $FFMPEG_ZIP $zip
        if (Test-Path $tam) { Remove-Item $tam -Recurse -Force }
        Expand-Archive $zip $tam -Force
        $d = Get-ChildItem $tam -Directory | Select-Object -First 1
        Move-Item $d.FullName "$GOC\ffmpeg"
        Remove-Item $zip, $tam -Recurse -Force -ErrorAction SilentlyContinue
    }
    & "$GOC\ffmpeg\bin\ffmpeg.exe" -hide_banner -version | Select-Object -First 1

    # ---------- 3. pyVideoTrans ----------
    Buoc "3/6 Tải pyVideoTrans"
    if (-not (Test-Path "$GOC\pyvideotrans\pyproject.toml")) {
        $zip = "$env:TEMP\dichvideo_pvt.zip"
        $tam = "$env:TEMP\dichvideo_pvt"
        TaiFile "https://github.com/jianchang512/pyvideotrans/archive/$PVT_COMMIT.zip" $zip
        if (Test-Path $tam) { Remove-Item $tam -Recurse -Force }
        Expand-Archive $zip $tam -Force
        $d = Get-ChildItem $tam -Directory | Select-Object -First 1
        Move-Item $d.FullName "$GOC\pyvideotrans"
        Remove-Item $zip, $tam -Recurse -Force -ErrorAction SilentlyContinue
    }

    # ---------- 4. Thư viện Python cho pyVideoTrans ----------
    Buoc "4/6 Cài thư viện Python cho pyVideoTrans (lâu nhất, ~3-5 GB, có thể 15-40 phút tuỳ mạng)"
    # File lớn nhất (torch cho card NVIDIA, ~3.3 GB) + pynini (trên GitHub) tải trước bằng curl -> tải tiếp được khi đứt.
    $GOI = "$GOC\goi_tai"
    New-Item -ItemType Directory -Force $GOI | Out-Null
    $TORCH = "$GOI\torch-2.7.1+cu128-cp310-cp310-win_amd64.whl"
    $PYNINI = "$GOI\pynini-2.1.6.post1-cp310-cp310-win_amd64.whl"
    Write-Host "Tải torch (~3.3 GB, tải tiếp được khi mạng đứt)..."
    TaiFile "https://download-r2.pytorch.org/whl/cu128/torch-2.7.1%2Bcu128-cp310-cp310-win_amd64.whl" $TORCH "5174f02de8ca14df87c8e333c4c39cf3ce93a323c9d470d690301d110a053b3c"
    TaiFile "https://github.com/billwuhao/pynini-windows-wheels/releases/download/v2.1.6.post1/pynini-2.1.6.post1-cp310-cp310-win_amd64.whl" $PYNINI "18be20f369f86355a12f9bad76bd17f1235df32cd72df6564f068b0e4f4f1911"
    $env:UV_HTTP_TIMEOUT = "600"; $env:UV_HTTP_RETRIES = "10"
    Push-Location "$GOC\pyvideotrans"
    foreach ($lan in 1..3) {
        if (Test-Path ".venv\Scripts\python.exe") { break }
        uv venv --python 3.10 .venv
        if ($LASTEXITCODE -ne 0) { Write-Host "Tải Python lỗi - thử lại sau 10 giây..." -ForegroundColor Yellow; Start-Sleep -Seconds 10 }
    }
    if (-not (Test-Path ".venv\Scripts\python.exe")) { throw "Không tải được Python 3.10 (mạng không ổn định - thử lại sau hoặc đổi mạng/4G)" }
    # Danh sách thư viện đúng phiên bản đã khoá; bỏ giọng Chatterbox (không dùng, phải tải qua Git);
    # torch + pynini lấy từ file đã tải sẵn.
    uv export --frozen --no-hashes --no-emit-project --no-dev --no-emit-package resemble-perth --no-emit-package chatterbox-tts -o "$GOI\thu_vien.txt"
    if ($LASTEXITCODE -ne 0) { throw "Không đọc được danh sách thư viện của pyVideoTrans" }
    $uriTorch = ([System.Uri]$TORCH).AbsoluteUri
    $uriPynini = ([System.Uri]$PYNINI).AbsoluteUri
    $ds = Get-Content "$GOI\thu_vien.txt" | ForEach-Object {
        if ($_ -match '^torch==2\.7\.1\+cu128') { "torch @ $uriTorch ; sys_platform == 'win32'" }
        elseif ($_ -match '^pynini @ ') { "pynini @ $uriPynini ; sys_platform == 'win32'" }
        else { $_ }
    }
    [System.IO.File]::WriteAllLines("$GOI\thu_vien_win.txt", $ds)
    $env:VIRTUAL_ENV = "$GOC\pyvideotrans\.venv"
    # Mạng chập chờn -> tự thử lại (các gói đã tải xong được giữ trong bộ nhớ đệm, lần sau không tải lại).
    $ok = $false
    foreach ($lan in 1..5) {
        # --no-deps: cài đúng y danh sách đã khoá (đã gồm mọi thư viện phụ), không giải lại phiên bản
        uv pip install -r "$GOI\thu_vien_win.txt" --no-deps --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
        if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        Write-Host "Mạng bị ngắt khi tải thư viện - thử lại lần $($lan + 1)/5 sau 10 giây (gói đã tải xong được giữ)..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
    }
    Remove-Item Env:VIRTUAL_ENV
    if (-not $ok) { throw "Cài thư viện lỗi (mạng không ổn định). Chạy lại CaiDat.bat - phần đã tải được giữ lại." }
    # tạo file cài đặt mặc định của pyVideoTrans (cảnh báo của Python không phải lỗi -> bỏ qua)
    $ErrorActionPreference = "Continue"
    & ".venv\Scripts\python.exe" -c "from videotrans.configure import config" *> $null
    $ErrorActionPreference = "Stop"
    Pop-Location
    # áp tinh chỉnh của tool: chia câu theo cụm lời + lồng tiếng 6 câu song song
    & "$GOC\pyvideotrans\.venv\Scripts\python.exe" "$GOC\cai_dat_cfg.py"

    # ---------- 5. Phần đọc chữ (OCR) + tải video ----------
    Buoc "5/6 Cài phần đọc chữ trên hình (OCR) và tải video"
    foreach ($lan in 1..3) {
        if (Test-Path "$GOC\.venv_tool\Scripts\python.exe") { break }
        uv venv --python 3.10 "$GOC\.venv_tool"
        if ($LASTEXITCODE -ne 0) { Write-Host "Tải Python lỗi - thử lại sau 10 giây..." -ForegroundColor Yellow; Start-Sleep -Seconds 10 }
    }
    if (-not (Test-Path "$GOC\.venv_tool\Scripts\python.exe")) { throw "Không tải được Python 3.10 (mạng không ổn định - thử lại sau hoặc đổi mạng/4G)" }
    $env:VIRTUAL_ENV = "$GOC\.venv_tool"
    $ok = $false
    foreach ($lan in 1..3) {
        # dùng chung file torch đã tải (bản cho card NVIDIA) -> AI xoá chữ / làm nét chạy bằng GPU nếu có
        uv pip install rapidocr onnxruntime opencv-python-headless numpy requests yt-dlp "$TORCH" --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
        if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        Write-Host "Mạng bị ngắt khi tải thư viện - thử lại lần $($lan + 1)/3 sau 10 giây..." -ForegroundColor Yellow
        Start-Sleep -Seconds 10
    }
    if (-not $ok) { throw "Cài thư viện OCR lỗi (mạng không ổn định - thử lại sau hoặc đổi mạng/4G)" }
    Remove-Item Env:VIRTUAL_ENV
    # Mô hình AI xoá chữ gốc (LaMa, ~200 MB). Tải lỗi thì tool tự dùng kiểu khung đen.
    New-Item -ItemType Directory -Force "$GOC\mo_hinh" | Out-Null
    if (-not (Test-Path "$GOC\mo_hinh\big-lama.pt")) {
        # curl có tự thử lại + tải tiếp từ chỗ bị đứt (mạng yếu không phải tải lại từ đầu)
        & curl.exe -fL --retry 10 --retry-delay 5 --retry-all-errors -C - -o "$GOC\mo_hinh\big-lama.pt.tam" "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt"
        if ($LASTEXITCODE -eq 0) {
            Move-Item -Force "$GOC\mo_hinh\big-lama.pt.tam" "$GOC\mo_hinh\big-lama.pt"
        } else {
            Write-Host "Chưa tải được mô hình AI xoá chữ - tạm dùng kiểu khung đen. Chạy lại CaiDat.bat để tải tiếp." -ForegroundColor Yellow
        }
    }
    # Mô hình AI làm nét video mờ (Real-ESRGAN, ~5 MB). Tải lỗi thì bỏ qua bước làm nét.
    if (-not (Test-Path "$GOC\mo_hinh\realesr-general-x4v3.pth")) {
        # curl có tự thử lại + tải tiếp từ chỗ bị đứt (mạng yếu không phải tải lại từ đầu)
        & curl.exe -fL --retry 10 --retry-delay 5 --retry-all-errors -C - -o "$GOC\mo_hinh\realesr-general-x4v3.pth.tam" "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"
        if ($LASTEXITCODE -eq 0) {
            Move-Item -Force "$GOC\mo_hinh\realesr-general-x4v3.pth.tam" "$GOC\mo_hinh\realesr-general-x4v3.pth"
        } else {
            Write-Host "Chưa tải được mô hình làm nét - bỏ qua bước làm nét. Chạy lại CaiDat.bat để tải tiếp." -ForegroundColor Yellow
        }
    }

    # ---------- 6. Thư mục + lối tắt ----------
    Buoc "6/6 Tạo lối tắt 'Dich Video' trên Desktop"
    New-Item -ItemType Directory -Force "$GOC\Video_Vao", "$GOC\Video_Ra" | Out-Null
    $ws = New-Object -ComObject WScript.Shell
    $lnk = $ws.CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\Dich Video.lnk")
    $lnk.TargetPath = "$GOC\Dich Video.bat"
    $lnk.WorkingDirectory = $GOC
    $lnk.WindowStyle = 7
    $lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,18"
    $lnk.Save()

    Write-Host "`n✔ CÀI ĐẶT XONG!" -ForegroundColor Green
    Write-Host "  • Mở tool: bấm đúp lối tắt 'Dich Video' trên Desktop (hoặc 'Dich Video.bat' trong thư mục này)."
    Write-Host "  • Lần dịch đầu tiên sẽ tự tải mô hình nghe (~3 GB), các lần sau nhanh."
    Write-Host "  • API key ai33 / DeepSeek (nếu có) nhập trên giao diện. Không có key vẫn dùng được"
    Write-Host "    Google Dịch + giọng Edge miễn phí."
    Write-Host "  • Hướng dẫn: HUONG_DAN.md"
}
catch {
    Write-Host "`n✖ Cài đặt bị lỗi: $_" -ForegroundColor Red
    Write-Host "  Chụp màn hình cửa sổ này gửi cho người đưa bạn bộ cài để được hỗ trợ."
}
