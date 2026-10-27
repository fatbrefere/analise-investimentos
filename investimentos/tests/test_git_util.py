import subprocess
from pathlib import Path

import pytest

from investimentos import git_util


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    origem = tmp_path / "origem.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origem))
    trabalho = tmp_path / "trabalho"
    _git(tmp_path, "clone", "-q", str(origem), str(trabalho))
    _git(trabalho, "config", "user.email", "t@t"); _git(trabalho, "config", "user.name", "t")
    (trabalho / "investimentos" / "data").mkdir(parents=True)
    (trabalho / "investimentos" / "data" / "macro.json").write_text('{"v": 1}')
    _git(trabalho, "add", "."); _git(trabalho, "commit", "-q", "-m", "inicial"); _git(trabalho, "push", "-q", "origin", "main")
    monkeypatch.setattr(git_util, "RAIZ", trabalho)
    return origem, trabalho


def test_baixar_dados_sobrescreve_locais(repos, tmp_path):
    origem, trabalho = repos
    # alguém (o workflow) publica dados novos
    outro = tmp_path / "outro"
    _git(tmp_path, "clone", "-q", str(origem), str(outro))
    _git(outro, "config", "user.email", "w@w"); _git(outro, "config", "user.name", "w")
    (outro / "investimentos" / "data" / "macro.json").write_text('{"v": 2}')
    _git(outro, "commit", "-q", "-am", "dados novos"); _git(outro, "push", "-q", "origin", "main")
    # localmente uma atualização falha e deixa o arquivo modificado
    (trabalho / "investimentos" / "data" / "macro.json").write_text('{"v": "local quebrado"}')
    msg = git_util.baixar_dados_do_github()
    assert "atualizados" in msg
    assert (trabalho / "investimentos" / "data" / "macro.json").read_text() == '{"v": 2}'
    assert _git(trabalho, "rev-parse", "HEAD") == _git(trabalho, "rev-parse", "origin/main")


def test_enviar_arquivos_para_branch_nao_toca_no_branch_atual(repos, tmp_path):
    origem, trabalho = repos
    relatorio = tmp_path / "rel.txt"; relatorio.write_text("tudo quebrado")
    (trabalho / "sujo.txt").write_text("alteração local não commitada")
    head_antes = _git(trabalho, "rev-parse", "HEAD")
    commit = git_util.enviar_arquivos_para_branch({"diagnostico/rel.txt": relatorio}, "diag")
    assert _git(trabalho, "rev-parse", "HEAD") == head_antes
    assert (trabalho / "sujo.txt").exists() and not (trabalho / "diagnostico").exists()
    assert _git(trabalho, "ls-remote", "origin", "refs/heads/diagnostico-local").startswith(commit)
    assert _git(trabalho, "show", f"{commit}:diagnostico/rel.txt") == "tudo quebrado"
