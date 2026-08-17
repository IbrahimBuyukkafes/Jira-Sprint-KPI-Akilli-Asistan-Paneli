@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo.
    echo [HATA] ".venv" sanal ortami bulunamadi veya aktive edilemedi.
    echo Once Kurulum.bat dosyasini calistirin.
    echo.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo.
    echo [HATA] ".venv" sanal ortami bulunamadi veya aktive edilemedi.
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
