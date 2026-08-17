@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   Jira Sprint ve KPI Panosu - Kurulum
echo ============================================
echo.

REM 1) Conda kurulu mu?
where conda >nul 2>&1
if errorlevel 1 (
    echo [HATA] Conda bulunamadi.
    echo.
    echo Once Miniconda'yi su adresten indirip kurun:
    echo   https://docs.conda.io/en/latest/miniconda.html
    echo Kurulumdan sonra bu dosyayi tekrar calistirin.
    echo.
    pause
    exit /b 1
)
echo [OK] Conda bulundu.

REM 2) "jira_mcp" adinda bir conda ortami var mi?
conda env list | findstr /b /c:"jira_mcp " >nul
if errorlevel 1 (
    echo [BILGI] "jira_mcp" adinda bir conda ortami bulunamadi, olusturuluyor...
    call conda create -n jira_mcp python=3.10 -y
    if errorlevel 1 (
        echo.
        echo [HATA] Conda ortami olusturulamadi. Yukaridaki hata mesajina bakin.
        pause
        exit /b 1
    )
    echo [OK] "jira_mcp" ortami olusturuldu.
) else (
    echo [OK] "jira_mcp" ortami zaten mevcut.
)

REM 3) Ortami aktive et ve bagimliliklari kur
echo.
echo Bagimliliklar kuruluyor (pip install -r requirements.txt)...
call conda activate jira_mcp
if errorlevel 1 (
    echo.
    echo [HATA] "jira_mcp" ortami aktive edilemedi.
    pause
    exit /b 1
)
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [HATA] Bagimliliklar kurulamadi. Yukaridaki hata mesajina bakin.
    pause
    exit /b 1
)
echo [OK] Bagimliliklar kuruldu.

REM 4) Ollama kurulu mu?
echo.
where ollama >nul 2>&1
if errorlevel 1 (
    echo [HATA] Ollama bulunamadi.
    echo.
    echo Once Ollama'yi su adresten indirip kurun:
    echo   https://ollama.com/download
    echo Kurulumdan sonra bu dosyayi tekrar calistirin.
    echo.
    pause
    exit /b 1
)
echo [OK] Ollama bulundu.

REM 5) "qwen2.5:3b" modeli cekilmis mi?
echo.
echo Ollama modelleri kontrol ediliyor...
ollama list | findstr /c:"qwen2.5:3b" >nul
if errorlevel 1 (
    echo [BILGI] "qwen2.5:3b" modeli bulunamadi, indiriliyor ^(yaklasik 2 GB, biraz surebilir^)...
    ollama pull qwen2.5:3b
    if errorlevel 1 (
        echo.
        echo [HATA] Model indirilemedi. Ollama servisinin calisir durumda oldugundan emin olun.
        pause
        exit /b 1
    )
    echo [OK] "qwen2.5:3b" modeli indirildi.
) else (
    echo [OK] "qwen2.5:3b" modeli zaten mevcut.
)

echo.
echo ============================================
echo   Kurulum tamamlandi!
echo   Artik Uygulamayi_Baslat.bat dosyasina cift
echo   tiklayarak uygulamayi acabilirsiniz.
echo ============================================
echo.
pause
exit /b 0
