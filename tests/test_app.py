"""
Testes de segurança e regras de negócio (pytest + cliente de teste do Flask).

Requisitos: base de dados com schema.sql + seed.sql carregados e .env configurado
(as contas de demonstração do seed são usadas nos testes).

    pip install pytest
    pytest -q
"""
import os
import re
import threading

import mysql.connector
import pytest

os.environ.setdefault("SECRET_KEY", "chave-de-testes")

from app import app, get_db_connection  # noqa: E402

PASSWORD = "Demo@2026"


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def csrf_token(client, url="/login"):
    html = client.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def login(client, email, password=PASSWORD):
    token = csrf_token(client)
    return client.post("/login", data={"email": email, "password": password, "csrf_token": token},
                       follow_redirects=False)


def db_one(sql, params=()):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute(sql, params)
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row


# ----------------------------- autenticação ----------------------------------
def test_login_valido_redireciona_admin_para_backoffice(client):
    resp = login(client, "super@exemplo.pt")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/admin")


def test_login_invalido_nao_inicia_sessao(client):
    resp = login(client, "super@exemplo.pt", "palavra-errada")
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_post_sem_token_csrf_e_rejeitado(client):
    resp = client.post("/login", data={"email": "super@exemplo.pt", "password": PASSWORD})
    assert resp.status_code == 302  # redirecionado com aviso; sessão NÃO iniciada
    with client.session_transaction() as sess:
        assert "user_id" not in sess


# ----------------------------- RBAC ------------------------------------------
def test_aluno_nao_acede_ao_backoffice(client):
    login(client, "aluno@exemplo.pt")
    resp = client.get("/admin")
    assert resp.status_code == 302 and "/admin" not in resp.headers["Location"]


def test_apagar_por_get_nao_e_permitido(client):
    login(client, "super@exemplo.pt")
    assert client.get("/admin/apagar_evento/1").status_code == 405


def test_admin_de_clube_nao_edita_eventos_de_outro_clube(client):
    login(client, "leitura@exemplo.pt")
    evento_teatro = db_one("SELECT id, titulo FROM eventos WHERE categoria = 'teatro' LIMIT 1")
    token = csrf_token(client, "/admin")
    client.post(f"/admin/editar_evento/{evento_teatro['id']}", data={
        "csrf_token": token, "titulo": "HACKED", "data_evento": "2030-01-01T10:00", "vagas_totais": "10",
    })
    assert db_one("SELECT titulo FROM eventos WHERE id = %s", (evento_teatro["id"],))["titulo"] == evento_teatro["titulo"]


def test_admin_de_clube_nao_apaga_eventos_de_outro_clube(client):
    login(client, "leitura@exemplo.pt")
    evento_teatro = db_one("SELECT id FROM eventos WHERE categoria = 'teatro' LIMIT 1")
    token = csrf_token(client, "/admin")
    client.post(f"/admin/apagar_evento/{evento_teatro['id']}", data={"csrf_token": token})
    assert db_one("SELECT id FROM eventos WHERE id = %s", (evento_teatro["id"],)) is not None


# ----------------------------- inscrições / vagas ----------------------------
def _criar_evento_com_vagas(vagas):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO eventos (titulo, data_evento, categoria, status, vagas_totais, vagas_ocupadas) "
        "VALUES ('Teste de concorrência', NOW() + INTERVAL 1 DAY, 'externo', 'agendado', %s, 0)", (vagas,))
    conn.commit()
    evento_id = cur.lastrowid
    cur.close()
    conn.close()
    return evento_id


def test_inscricoes_simultaneas_nao_ultrapassam_a_lotacao():
    """20 convidados a inscreverem-se ao mesmo tempo num evento com 3 vagas: só 3 entram."""
    evento_id = _criar_evento_com_vagas(3)
    resultados = []

    def inscrever(n):
        with app.test_client() as c:
            token = csrf_token(c)
            c.post(f"/inscrever_convidado/{evento_id}", data={
                "csrf_token": token, "nome_convidado": f"Convidado {n}", "email_convidado": f"c{n}@exemplo.pt"})
            resultados.append(n)

    threads = [threading.Thread(target=inscrever, args=(n,)) for n in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    evento = db_one("SELECT vagas_totais, vagas_ocupadas FROM eventos WHERE id = %s", (evento_id,))
    inscritos = db_one("SELECT COUNT(*) AS n FROM inscricoes WHERE evento_id = %s", (evento_id,))["n"]
    assert evento["vagas_ocupadas"] == 3
    assert inscritos == 3


def test_inscricao_duplicada_nao_consome_vaga(client):
    evento_id = _criar_evento_com_vagas(5)
    login(client, "aluno@exemplo.pt")
    for _ in range(2):
        token = csrf_token(client, f"/evento/{evento_id}")
        client.post(f"/inscrever/{evento_id}", data={"csrf_token": token})
    assert db_one("SELECT vagas_ocupadas FROM eventos WHERE id = %s", (evento_id,))["vagas_ocupadas"] == 1
