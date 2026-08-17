@echo off
cd /d "%~dp0"

call conda activate jira_mcp
if errorlevel 1 (
    echo.
    echo [HATA] "jira_mcp" adinda bir conda ortami bulunamadi veya aktive edilemedi.
    echo Once Kurulum.bat dosyasini calistirin.
    echo.
    pause
    exit /b 1
)

echo Uygulama baslatiliyor, tarayicinizda otomatik acilacak...
echo Kapatmak icin bu pencereyi kapatabilir veya Ctrl+C'ye basabilirsiniz.
echo.
streamlit run app\new_dashboard.py

echo.
echo Uygulama kapandi.
pause
