@echo off
echo ==================================================
echo Iniciando o sistema de Despesas de Viagem...
echo ==================================================
echo.

:: Força o Python a rodar o módulo do Streamlit diretamente
python -m streamlit run app.py

pause
