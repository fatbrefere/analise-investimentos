@echo off
cd /d "%~dp0"
echo Atualizando dados de investimentos (pode levar alguns minutos)...
python -m investimentos.atualizar
echo.
echo Abrindo o painel...
streamlit run investimentos\app_investimentos.py
pause
