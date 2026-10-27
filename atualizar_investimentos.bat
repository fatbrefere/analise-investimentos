@echo off
cd /d "%~dp0"
python -m investimentos.atualizar >> investimentos\data\atualizacao.log 2>&1
