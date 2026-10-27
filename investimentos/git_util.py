"""
Operações de Git usadas pelo painel: baixar os dados prontos do GitHub e
enviar o diagnóstico local para um branch separado, sem mexer no branch de
trabalho nem nos arquivos do usuário.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from investimentos import config

RAIZ = config.PASTA_BASE.parent
BRANCH_DIAGNOSTICO = "diagnostico-local"


def _git(*args: str, env: dict | None = None, check: bool = True) -> str:
    ambiente = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
    proc = subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, env=ambiente)
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def e_repositorio() -> bool:
    try:
        return _git("rev-parse", "--is-inside-work-tree") == "true"
    except Exception:  # noqa: BLE001
        return False


def baixar_dados_do_github(remoto: str = "origin", branch: str = "main") -> str:
    """Traz investimentos/data do GitHub (sobrescrevendo os locais) e, se possível, o código mais novo."""
    _git("fetch", remoto, branch)
    _git("checkout", f"{remoto}/{branch}", "--", "investimentos/data")
    try:
        _git("merge", "--ff-only", f"{remoto}/{branch}")
        return "Dados e código atualizados a partir do GitHub."
    except RuntimeError as erro:
        return f"Dados atualizados a partir do GitHub. O código não pôde ser atualizado automaticamente ({erro}); rode `git pull` no terminal."


def enviar_arquivos_para_branch(arquivos: dict[str, Path], mensagem: str, remoto: str = "origin", branch: str = BRANCH_DIAGNOSTICO, base: str = "main") -> str:
    """Cria um commit com os arquivos dados em cima de origin/<base> e envia para <branch>.

    Usa um índice temporário, então o branch atual e os arquivos de trabalho
    do usuário ficam intocados. Retorna o hash do commit enviado.
    """
    _git("fetch", remoto, base)
    with tempfile.TemporaryDirectory() as pasta:
        indice = {"GIT_INDEX_FILE": str(Path(pasta) / "index")}
        _git("read-tree", f"{remoto}/{base}", env=indice)
        for caminho_no_repo, arquivo in arquivos.items():
            blob = _git("hash-object", "-w", str(arquivo))
            _git("update-index", "--add", "--cacheinfo", f"100644,{blob},{caminho_no_repo}", env=indice)
        arvore = _git("write-tree", env=indice)
    commit = _git(
        "commit-tree", arvore, "-p", f"{remoto}/{base}", "-m", mensagem,
        env={"GIT_AUTHOR_NAME": "diagnostico", "GIT_AUTHOR_EMAIL": "diagnostico@local", "GIT_COMMITTER_NAME": "diagnostico", "GIT_COMMITTER_EMAIL": "diagnostico@local"},
    )
    _git("push", "--force", remoto, f"{commit}:refs/heads/{branch}")
    return commit
