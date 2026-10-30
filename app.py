"""
Laboratório Cultural - plataforma web de gestão de eventos, clubes de leitura
e teatro (projeto académico).

Stack: Flask + Jinja2 + MySQL/MariaDB (mysql-connector-python).

Estrutura (ficheiro único, organizado por secções):
    1. Configuração e segurança   (variáveis de ambiente, CSRF, cabeçalhos)
    2. Acesso à base de dados     (ligação + gestor de contexto transacional)
    3. Utilitários e permissões   (decoradores, RBAC, validação de inputs)
    4. Rotas públicas             (home, clubes, eventos externos, detalhes)
    5. Autenticação e perfil      (login, registo, perfil, logout)
    6. Inscrições                 (eventos e clubes, com controlo atómico de vagas)
    7. Backoffice                 (CRUD de eventos, notícias, livros, utilizadores, categorias)
"""
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode, urlparse

import mysql.connector
from dotenv import load_dotenv
from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

# =============================================================================
# 1. CONFIGURAÇÃO E SEGURANÇA
# =============================================================================
app = Flask(__name__)

_secret_key = os.environ.get("SECRET_KEY")
if not _secret_key:
    raise RuntimeError(
        "SECRET_KEY não definida. Copia .env.example para .env e define um valor "
        "aleatório (ex.: python -c \"import secrets; print(secrets.token_hex(32))\")."
    )

app.config.update(
    SECRET_KEY=_secret_key,
    MAX_CONTENT_LENGTH=1 * 1024 * 1024,          # limita o tamanho dos pedidos (1 MB)
    SESSION_COOKIE_HTTPONLY=True,                # o JavaScript não lê o cookie de sessão
    SESSION_COOKIE_SAMESITE="Lax",               # mitiga CSRF entre sites
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",  # 1 em HTTPS
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)

# Proteção CSRF: valida o token em todos os pedidos POST.
csrf = CSRFProtect(app)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Papéis (RBAC) e constantes de domínio
ROLES = ("super_admin", "admin_leitura", "admin_teatro", "aluno")
STAFF_ROLES = ("super_admin", "admin_leitura", "admin_teatro")
ROLE_CATEGORY = {"admin_leitura": "leitura", "admin_teatro": "teatro"}  # âmbito de cada admin de clube
CORE_CATEGORIES = ("leitura", "teatro", "externo")  # usadas em rotas fixas: não podem ser renomeadas/apagadas
EVENT_STATUS = ("agendado", "realizado", "cancelado")
NEWS_STATUS = ("rascunho", "publicado")
MIN_PASSWORD_LENGTH = 8
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.after_request
def set_security_headers(response):
    """Cabeçalhos HTTP de segurança básicos."""
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


# =============================================================================
# 2. ACESSO À BASE DE DADOS
# =============================================================================
def get_db_connection():
    """Abre uma ligação ao MySQL/MariaDB com credenciais vindas do ambiente."""
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "lab_user"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "lab_cultural"),
    )


@contextmanager
def get_cursor(dictionary=True):
    """
    Gestor de contexto transacional.

    - Faz COMMIT se o bloco terminar sem erro;
    - Faz ROLLBACK se ocorrer uma exceção (e volta a propagá-la);
    - Fecha sempre o cursor e a ligação.
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=dictionary, buffered=True)
    try:
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def flash_db_error(action):
    """
    Regista o erro técnico no log do servidor e mostra uma mensagem genérica
    ao utilizador (nunca expõe detalhes internos da base de dados).
    Deve ser chamada dentro de um bloco `except`.
    """
    app.logger.exception("Erro de base de dados ao %s", action)
    flash("Ocorreu um erro inesperado. Tenta novamente mais tarde.", "danger")


# =============================================================================
# 3. UTILITÁRIOS E PERMISSÕES
# =============================================================================
def safe_back(default_endpoint="lab_cultural"):
    """
    Redireciona para a página anterior apenas se for do mesmo site
    (evita open redirect através do cabeçalho Referer).
    """
    ref = request.referrer
    if ref:
        parsed = urlparse(ref)
        if parsed.netloc == request.host:
            return redirect(ref)
    return redirect(url_for(default_endpoint))


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Precisas de iniciar sessão para aceder a esta página.", "danger")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def roles_required(*roles):
    """Restringe uma rota a um conjunto de papéis (RBAC)."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Precisas de iniciar sessão para aceder a esta página.", "danger")
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("Não tens permissão para realizar esta ação.", "danger")
                return redirect(url_for("admin_dashboard") if session.get("role") in STAFF_ROLES
                                else url_for("lab_cultural"))
            return view(*args, **kwargs)
        return wrapper
    return decorator


staff_required = roles_required(*STAFF_ROLES)


def can_manage_category(role, categoria):
    """O super admin gere tudo; cada admin de clube só gere a sua categoria."""
    return role == "super_admin" or ROLE_CATEGORY.get(role) == categoria


def form_text(name, max_len=None, default=None):
    """Lê um campo de texto do formulário (sem espaços nas pontas); vazio -> default."""
    value = (request.form.get(name) or "").strip()
    if not value:
        return default
    return value[:max_len] if max_len else value


def form_int(name, default=None, minimum=None):
    """Lê um inteiro do formulário; devolve default se inválido."""
    try:
        value = int(request.form.get(name, ""))
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def form_datetime(name):
    """Lê um datetime (formato ISO do input datetime-local); None se inválido."""
    raw = (request.form.get(name) or "").strip()
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def form_url(name):
    """Aceita apenas URLs http(s) (evita esquemas perigosos como javascript:)."""
    value = form_text(name, max_len=255)
    if value and urlparse(value).scheme in ("http", "https"):
        return value
    return None


def valid_email(email):
    return bool(email) and len(email) <= 50 and EMAIL_RE.match(email) is not None


def is_duplicate(error):
    """True se o erro for uma violação de chave única (MySQL errno 1062)."""
    return getattr(error, "errno", None) == 1062


def category_exists(nome):
    with get_cursor() as (_, cur):
        cur.execute("SELECT 1 FROM categorias WHERE nome = %s", (nome,))
        return cur.fetchone() is not None


@app.context_processor
def inject_roles():
    """Disponibiliza constantes úteis a todos os templates."""
    return {"STAFF_ROLES": STAFF_ROLES}


# =============================================================================
# 4. ROTAS PÚBLICAS
# =============================================================================
@app.route("/")
def portal():
    return redirect(url_for("lab_cultural"))


@app.route("/lab_cultural")
def lab_cultural():
    """Home page: missão do laboratório e próximos eventos em destaque."""
    with get_cursor() as (_, cur):
        cur.execute(
            """
            SELECT * FROM eventos
            WHERE status = 'agendado' AND DATE(data_evento) >= CURRENT_DATE()
            ORDER BY data_evento ASC
            LIMIT 3
            """
        )
        eventos_destaque = cur.fetchall()
    return render_template("lab_cultural.html", eventos_destaque=eventos_destaque)


def _is_member(table, user_id):
    """Indica se o utilizador pertence a um clube (tabela fixa, nunca vinda do utilizador)."""
    with get_cursor() as (_, cur):
        cur.execute(f"SELECT 1 FROM {table} WHERE user_id = %s", (user_id,))  # noqa: S608 (table é constante)
        return cur.fetchone() is not None


@app.route("/leitura")
def leitura():
    is_membro = "user_id" in session and _is_member("membros_clube_leitura", session["user_id"])
    with get_cursor() as (_, cur):
        cur.execute("SELECT * FROM eventos WHERE categoria = 'leitura' AND status = 'agendado' ORDER BY data_evento ASC")
        eventos = cur.fetchall()
        cur.execute(
            "SELECT * FROM noticias WHERE categoria = 'leitura' AND status = 'publicado' "
            "ORDER BY data_publicacao DESC LIMIT 5"
        )
        noticias = cur.fetchall()
        cur.execute("SELECT * FROM livros WHERE status = 'destaque' ORDER BY data_criacao DESC")
        livros = cur.fetchall()
    return render_template("leitura.html", eventos=eventos, noticias=noticias, livros=livros, is_membro=is_membro)


@app.route("/teatro")
def teatro():
    is_membro = "user_id" in session and _is_member("membros_clube_teatro", session["user_id"])
    with get_cursor() as (_, cur):
        cur.execute("SELECT * FROM eventos WHERE categoria = 'teatro' AND status = 'agendado' ORDER BY data_evento ASC")
        eventos = cur.fetchall()
        cur.execute("SELECT * FROM noticias WHERE categoria = 'teatro' AND status = 'publicado' ORDER BY id DESC")
        noticias = cur.fetchall()
    return render_template("teatro.html", eventos=eventos, noticias=noticias, is_membro=is_membro)


@app.route("/externos")
def externos():
    """Agenda de eventos externos com filtros por distrito, cidade, data e tipo."""
    distrito = request.args.get("distrito", "")
    cidade = request.args.get("cidade", "")
    data = request.args.get("data", "")
    tipo = request.args.get("tipo", "")

    # A query é construída a partir de fragmentos fixos; os valores vão sempre como parâmetros.
    query = "SELECT * FROM eventos WHERE categoria = 'externo' AND status = 'agendado'"
    params = []
    if distrito and distrito != "todos":
        query += " AND distrito = %s"
        params.append(distrito)
    if cidade and cidade != "todas":
        query += " AND cidade = %s"
        params.append(cidade)
    if data:
        query += " AND DATE(data_evento) >= %s"
        params.append(data)
    if tipo and tipo != "todos":
        query += " AND tipo_evento = %s"
        params.append(tipo)
    query += " ORDER BY data_evento ASC"

    with get_cursor() as (_, cur):
        cur.execute(
            "SELECT DISTINCT tipo_evento FROM eventos WHERE categoria = 'externo' AND tipo_evento IS NOT NULL"
        )
        tipos_disponiveis = [row["tipo_evento"] for row in cur.fetchall()]
        cur.execute(query, tuple(params))
        eventos = cur.fetchall()

    return render_template(
        "externos.html",
        eventos=eventos,
        distrito_selecionado=distrito,
        cidade_selecionada=cidade,
        data_selecionada=data,
        tipo_selecionado=tipo,
        tipos_disponiveis=tipos_disponiveis,
    )


@app.route("/noticia/<int:id>")
def noticia_detalhe(id):
    with get_cursor() as (_, cur):
        cur.execute(
            """
            SELECT n.*, u.nome_real AS autor
            FROM noticias n
            LEFT JOIN utilizadores u ON n.autor_id = u.id
            WHERE n.id = %s
            """,
            (id,),
        )
        noticia = cur.fetchone()

    # Rascunhos só são visíveis para a equipa de gestão.
    if not noticia or (noticia["status"] != "publicado" and session.get("role") not in STAFF_ROLES):
        flash("Notícia não encontrada.", "danger")
        return redirect(url_for("lab_cultural"))
    return render_template("noticia_template.html", noticia=noticia)


def build_google_calendar_url(evento):
    """Gera o link 'Adicionar ao Google Calendar' (duração padrão: 1 hora)."""
    start = evento["data_evento"]
    if not hasattr(start, "strftime"):
        return ""
    end = start + timedelta(hours=1)
    local = ", ".join(part for part in (evento.get("local"), evento.get("cidade")) if part)
    params = {
        "action": "TEMPLATE",
        "text": evento["titulo"],
        "dates": f"{start.strftime('%Y%m%dT%H%M%S')}/{end.strftime('%Y%m%dT%H%M%S')}",
        "details": evento.get("descricao") or "",
        "location": local,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


@app.route("/evento/<int:id>")
def evento_detalhe(id):
    with get_cursor() as (_, cur):
        cur.execute(
            """
            SELECT e.*, u.nome_real AS autor
            FROM eventos e
            LEFT JOIN utilizadores u ON e.autor_id = u.id
            WHERE e.id = %s
            """,
            (id,),
        )
        evento = cur.fetchone()

        ja_inscrito = False
        if evento and "user_id" in session:
            cur.execute(
                "SELECT 1 FROM inscricoes WHERE evento_id = %s AND user_id = %s",
                (evento["id"], session["user_id"]),
            )
            ja_inscrito = cur.fetchone() is not None

    if not evento:
        flash("Evento não encontrado.", "danger")
        return redirect(url_for("lab_cultural"))

    return render_template(
        "evento_template.html",
        evento=evento,
        ja_inscrito=ja_inscrito,
        google_cal_url=build_google_calendar_url(evento),
    )


@app.route("/livro/<int:id>")
def livro_detalhe(id):
    with get_cursor() as (_, cur):
        cur.execute("SELECT * FROM livros WHERE id = %s", (id,))
        livro = cur.fetchone()
    if not livro:
        flash("Livro não encontrado.", "danger")
        return redirect(url_for("leitura"))
    return render_template("livro_template.html", livro=livro)


# =============================================================================
# 5. AUTENTICAÇÃO E PERFIL
# =============================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("admin_dashboard") if session.get("role") in STAFF_ROLES
                        else url_for("lab_cultural"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        try:
            with get_cursor() as (_, cur):
                cur.execute("SELECT * FROM utilizadores WHERE email = %s AND ativo = 1", (email,))
                user = cur.fetchone()
        except mysql.connector.Error:
            flash_db_error("iniciar sessão")
            return render_template("login.html")

        # Mensagem única para email inexistente e password errada (não revela contas existentes).
        if user and check_password_hash(user["password_hash"], password):
            session.clear()  # nova sessão após login (evita session fixation)
            session.permanent = True
            session["user"] = user["email"]
            session["user_id"] = user["id"]
            session["role"] = user["role"] or "aluno"
            session["nome_real"] = user["nome_real"]
            flash(f"Bem-vindo(a), {user['nome_real']}!", "success")
            if session["role"] in STAFF_ROLES:
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("lab_cultural"))
        flash("E-mail ou palavra-passe incorretos. Tenta novamente.", "danger")

    return render_template("login.html")


@app.route("/registo", methods=["GET", "POST"])
def registo():
    if "user_id" in session:
        return redirect(url_for("lab_cultural"))

    if request.method == "POST":
        nome = form_text("nome_real", max_len=100)
        email = (form_text("email", max_len=50) or "").lower()
        password = request.form.get("password") or ""
        password_confirm = request.form.get("password_confirm") or ""

        if not nome or not email or not password:
            flash("Por favor, preenche todos os campos obrigatórios.", "danger")
        elif not valid_email(email):
            flash("Introduz um endereço de e-mail válido.", "danger")
        elif len(password) < MIN_PASSWORD_LENGTH:
            flash(f"A palavra-passe deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.", "danger")
        elif password != password_confirm:
            flash("As palavras-passe introduzidas não coincidem. Tenta novamente.", "danger")
        else:
            try:
                with get_cursor() as (_, cur):
                    # Registo público: o papel é sempre 'aluno' (nunca vem do formulário).
                    cur.execute(
                        "INSERT INTO utilizadores (nome_real, email, password_hash, role) VALUES (%s, %s, %s, 'aluno')",
                        (nome, email, generate_password_hash(password)),
                    )
                flash("Conta criada com sucesso! Já podes efetuar o teu login.", "success")
                return redirect(url_for("login"))
            except mysql.connector.IntegrityError:
                flash("Este endereço de e-mail já se encontra registado.", "danger")
            except mysql.connector.Error:
                flash_db_error("registar utilizador")
        return redirect(url_for("registo"))

    return render_template("registo.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("lab_cultural"))


@app.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    user_id = session["user_id"]

    if request.method == "POST":
        nome = form_text("nome_real", max_len=100)
        email = (form_text("email", max_len=50) or "").lower()
        nova_password = request.form.get("password") or ""

        if not nome or not valid_email(email):
            flash("Nome e e-mail válidos são obrigatórios.", "danger")
        elif nova_password.strip() and len(nova_password) < MIN_PASSWORD_LENGTH:
            flash(f"A palavra-passe deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.", "danger")
        else:
            try:
                with get_cursor() as (_, cur):
                    if nova_password.strip():
                        cur.execute(
                            "UPDATE utilizadores SET nome_real = %s, email = %s, password_hash = %s WHERE id = %s",
                            (nome, email, generate_password_hash(nova_password), user_id),
                        )
                    else:
                        cur.execute(
                            "UPDATE utilizadores SET nome_real = %s, email = %s WHERE id = %s",
                            (nome, email, user_id),
                        )
                session["user"] = email
                session["nome_real"] = nome
                flash("Os teus dados foram atualizados com sucesso!", "success")
            except mysql.connector.IntegrityError:
                flash("Esse e-mail já está a ser usado por outra conta.", "danger")
            except mysql.connector.Error:
                flash_db_error("atualizar perfil")
        return redirect(url_for("perfil"))

    with get_cursor() as (_, cur):
        cur.execute("SELECT id, nome_real, email, role FROM utilizadores WHERE id = %s", (user_id,))
        utilizador = cur.fetchone()
        cur.execute(
            """
            SELECT e.* FROM inscricoes i
            JOIN eventos e ON i.evento_id = e.id
            WHERE i.user_id = %s
            ORDER BY e.data_evento ASC
            """,
            (user_id,),
        )
        eventos_inscritos = cur.fetchall()

    if not utilizador:  # conta removida entretanto
        session.clear()
        return redirect(url_for("login"))
    return render_template("perfil.html", utilizador=utilizador, eventos=eventos_inscritos)


# =============================================================================
# 6. INSCRIÇÕES
# =============================================================================
def _join_club(table, label, endpoint):
    """Inscreve o utilizador num clube (a tabela vem sempre de uma constante)."""
    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute(f"INSERT INTO {table} (user_id) VALUES (%s)", (session["user_id"],))  # noqa: S608
        flash(f"Parabéns! Já fazes parte do nosso Clube de {label}.", "success")
    except mysql.connector.IntegrityError:
        flash(f"Já te encontras inscrito no Clube de {label}.", "info")
    except mysql.connector.Error:
        flash_db_error("inscrever no clube")
    return redirect(url_for(endpoint))


@app.route("/inscrever_clube_leitura", methods=["POST"])
@login_required
def inscrever_clube_leitura():
    return _join_club("membros_clube_leitura", "Leitura", "leitura")


@app.route("/inscrever_clube_teatro", methods=["POST"])
@login_required
def inscrever_clube_teatro():
    return _join_club("membros_clube_teatro", "Teatro", "teatro")


def reservar_vaga(cur, evento_id):
    """
    Reserva uma vaga de forma ATÓMICA.

    Em vez de "ler as vagas e depois atualizar" (que permite overbooking quando
    dois pedidos chegam em simultâneo), a condição é verificada dentro do próprio
    UPDATE: só incrementa se ainda houver vagas. O MySQL bloqueia a linha durante
    a operação, por isso dois pedidos concorrentes nunca ultrapassam a lotação.

    Devolve True se a vaga foi reservada, False se o evento não existe, não está
    agendado ou está esgotado.
    """
    cur.execute(
        """
        UPDATE eventos
        SET vagas_ocupadas = vagas_ocupadas + 1
        WHERE id = %s AND status = 'agendado' AND vagas_ocupadas < vagas_totais
        """,
        (evento_id,),
    )
    return cur.rowcount == 1


def _motivo_sem_vaga(evento_id):
    with get_cursor() as (_, cur):
        cur.execute("SELECT status FROM eventos WHERE id = %s", (evento_id,))
        evento = cur.fetchone()
    if not evento:
        return "Evento não encontrado.", "danger"
    if evento["status"] != "agendado":
        return "Este evento já não aceita inscrições.", "warning"
    return "As vagas para este evento já esgotaram.", "warning"


@app.route("/inscrever/<int:evento_id>", methods=["POST"])
@login_required
def inscrever_utilizador(evento_id):
    try:
        with get_cursor() as (conn, cur):
            if not reservar_vaga(cur, evento_id):
                conn.rollback()
                msg, cat = _motivo_sem_vaga(evento_id)
                flash(msg, cat)
                return safe_back()
            # UNIQUE (evento_id, user_id) impede inscrições duplicadas, mesmo em pedidos simultâneos.
            cur.execute(
                "INSERT INTO inscricoes (evento_id, user_id) VALUES (%s, %s)",
                (evento_id, session["user_id"]),
            )
        flash("Inscrição confirmada!", "success")
    except mysql.connector.IntegrityError as err:
        # A exceção faz ROLLBACK, por isso a vaga reservada acima é devolvida automaticamente.
        if is_duplicate(err):
            flash("Já te encontras inscrito neste evento!", "info")
        else:
            flash_db_error("processar inscrição")
    except mysql.connector.Error:
        flash_db_error("processar inscrição")
    return safe_back()


@app.route("/inscrever_convidado/<int:evento_id>", methods=["POST"])
def inscrever_convidado(evento_id):
    nome = form_text("nome_convidado", max_len=150)
    email = (form_text("email_convidado", max_len=150) or "").lower()

    if not nome or not email:
        flash("Por favor, preenche todos os campos obrigatórios.", "danger")
        return safe_back()
    if not EMAIL_RE.match(email):
        flash("Introduz um endereço de e-mail válido.", "danger")
        return safe_back()

    try:
        with get_cursor() as (conn, cur):
            if not reservar_vaga(cur, evento_id):
                conn.rollback()
                msg, cat = _motivo_sem_vaga(evento_id)
                flash(msg, cat)
                return safe_back()
            cur.execute(
                "INSERT INTO inscricoes (evento_id, user_id, nome_convidado, email_convidado) "
                "VALUES (%s, NULL, %s, %s)",
                (evento_id, nome, email),
            )
        flash("Inscrição de convidado efetuada com sucesso!", "success")
    except mysql.connector.IntegrityError as err:
        if is_duplicate(err):
            flash("Este endereço de e-mail já se encontra inscrito neste evento!", "warning")
        else:
            flash_db_error("processar inscrição de convidado")
    except mysql.connector.Error:
        flash_db_error("processar inscrição de convidado")
    return safe_back()


# =============================================================================
# 7. BACKOFFICE
# =============================================================================
@app.route("/admin")
@staff_required
def admin_dashboard():
    cargo = session["role"]
    eventos, noticias, utilizadores, livros = [], [], [], []

    with get_cursor() as (_, cur):
        cur.execute("SELECT * FROM categorias ORDER BY nome ASC")
        categorias = cur.fetchall()

        if cargo == "super_admin":
            cur.execute("SELECT * FROM eventos ORDER BY data_evento DESC")
            eventos = cur.fetchall()
            cur.execute("SELECT * FROM noticias ORDER BY data_publicacao DESC")
            noticias = cur.fetchall()
            cur.execute("SELECT id, nome_real, email, role, ativo FROM utilizadores ORDER BY role, nome_real")
            utilizadores = cur.fetchall()
            cur.execute("SELECT * FROM livros ORDER BY data_criacao DESC")
            livros = cur.fetchall()
        else:
            categoria = ROLE_CATEGORY[cargo]
            cur.execute("SELECT * FROM eventos WHERE categoria = %s ORDER BY data_evento DESC", (categoria,))
            eventos = cur.fetchall()
            cur.execute("SELECT * FROM noticias WHERE categoria = %s ORDER BY data_publicacao DESC", (categoria,))
            noticias = cur.fetchall()
            if cargo == "admin_leitura":
                cur.execute("SELECT * FROM livros ORDER BY data_criacao DESC")
                livros = cur.fetchall()

    return render_template(
        "admin.html",
        eventos=eventos, noticias=noticias, utilizadores=utilizadores,
        livros=livros, categorias=categorias, cargo=cargo,
    )


def _resolve_category(role):
    """
    Categoria a usar ao criar/editar conteúdos:
    admins de clube ficam sempre limitados à sua categoria; o super admin pode
    escolher qualquer categoria existente.
    """
    if role in ROLE_CATEGORY:
        return ROLE_CATEGORY[role]
    categoria = form_text("categoria", max_len=100)
    return categoria if categoria and category_exists(categoria) else None


# ----------------------------- EVENTOS ---------------------------------------
@app.route("/admin/adicionar_evento", methods=["POST"])
@staff_required
def adicionar_evento():
    role = session["role"]
    titulo = form_text("titulo", max_len=100)
    data_evento = form_datetime("data_evento")
    categoria = _resolve_category(role)
    vagas = form_int("vagas_totais", default=0, minimum=0)

    if not titulo or not data_evento or not categoria:
        flash("Título, data e categoria válidos são obrigatórios.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute(
                """
                INSERT INTO eventos (titulo, descricao, data_evento, local, distrito, cidade, categoria,
                                     status, vagas_totais, vagas_ocupadas, autor_id, tipo_evento, imagem_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'agendado', %s, 0, %s, %s, %s)
                """,
                (titulo, form_text("descricao"), data_evento, form_text("local", 100),
                 form_text("distrito", 100), form_text("cidade", 100), categoria, vagas,
                 session["user_id"], form_text("tipo_evento", 50, "Outro"), form_url("imagem_url")),
            )
        flash("Evento adicionado com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("criar evento")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/editar_evento/<int:id>", methods=["POST"])
@staff_required
def editar_evento(id):
    role = session["role"]
    titulo = form_text("titulo", max_len=100)
    data_evento = form_datetime("data_evento")
    vagas = form_int("vagas_totais", minimum=0)
    status = form_text("status")

    if not titulo or not data_evento or vagas is None or (status and status not in EVENT_STATUS):
        flash("Dados do evento inválidos.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT categoria, status, vagas_ocupadas FROM eventos WHERE id = %s", (id,))
            atual = cur.fetchone()
            # Permissão: o evento atual E a categoria pedida têm de estar no âmbito do utilizador.
            if not atual or not can_manage_category(role, atual["categoria"]):
                flash("Não tens permissão para editar este evento.", "danger")
                return redirect(url_for("admin_dashboard"))

            categoria = atual["categoria"] if role in ROLE_CATEGORY else (form_text("categoria") or atual["categoria"])
            if not can_manage_category(role, categoria) or (role == "super_admin" and not category_exists(categoria)):
                flash("Categoria inválida.", "danger")
                return redirect(url_for("admin_dashboard"))
            if vagas < atual["vagas_ocupadas"]:
                flash(f"A lotação não pode ser inferior às inscrições já feitas ({atual['vagas_ocupadas']}).", "danger")
                return redirect(url_for("admin_dashboard"))

            cur.execute(
                """
                UPDATE eventos
                SET titulo = %s, descricao = %s, data_evento = %s, local = %s, distrito = %s, cidade = %s,
                    vagas_totais = %s, categoria = %s, status = %s, tipo_evento = %s, imagem_url = %s
                WHERE id = %s
                """,
                (titulo, form_text("descricao"), data_evento, form_text("local", 100),
                 form_text("distrito", 100), form_text("cidade", 100), vagas, categoria,
                 status or atual["status"], form_text("tipo_evento", 50, "Outro"), form_url("imagem_url"), id),
            )
        flash("Evento atualizado com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("atualizar evento")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apagar_evento/<int:id>", methods=["POST"])
@staff_required
def apagar_evento(id):
    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT categoria FROM eventos WHERE id = %s", (id,))
            evento = cur.fetchone()
            if not evento:
                flash("Evento não encontrado.", "danger")
            elif not can_manage_category(session["role"], evento["categoria"]):
                flash("Não tens permissão para apagar este evento.", "danger")
            else:
                cur.execute("DELETE FROM eventos WHERE id = %s", (id,))
                flash("Evento removido com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("apagar evento")
    return redirect(url_for("admin_dashboard"))


# ----------------------------- NOTÍCIAS --------------------------------------
@app.route("/admin/adicionar_noticia", methods=["POST"])
@staff_required
def adicionar_noticia():
    titulo = form_text("titulo", max_len=150)
    categoria = _resolve_category(session["role"])
    status = form_text("status", default="publicado")

    if not titulo or not categoria or status not in NEWS_STATUS:
        flash("Título, categoria e estado válidos são obrigatórios.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute(
                "INSERT INTO noticias (titulo, conteudo, categoria, status, data_publicacao, autor_id, imagem_url) "
                "VALUES (%s, %s, %s, %s, NOW(), %s, %s)",
                (titulo, form_text("conteudo"), categoria, status, session["user_id"], form_url("imagem_url")),
            )
        flash("Notícia guardada com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("criar notícia")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/editar_noticia/<int:id>", methods=["POST"])
@staff_required
def editar_noticia(id):
    role = session["role"]
    titulo = form_text("titulo", max_len=150)
    status = form_text("status")
    if not titulo or status not in NEWS_STATUS:
        flash("Dados da notícia inválidos.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT categoria FROM noticias WHERE id = %s", (id,))
            atual = cur.fetchone()
            if not atual or not can_manage_category(role, atual["categoria"]):
                flash("Não tens permissão para editar esta notícia.", "danger")
                return redirect(url_for("admin_dashboard"))

            categoria = atual["categoria"] if role in ROLE_CATEGORY else (form_text("categoria") or atual["categoria"])
            if role == "super_admin" and not category_exists(categoria):
                flash("Categoria inválida.", "danger")
                return redirect(url_for("admin_dashboard"))

            cur.execute(
                "UPDATE noticias SET titulo = %s, conteudo = %s, categoria = %s, status = %s, imagem_url = %s "
                "WHERE id = %s",
                (titulo, form_text("conteudo"), categoria, status, form_url("imagem_url"), id),
            )
        flash("Notícia atualizada!", "success")
    except mysql.connector.Error:
        flash_db_error("atualizar notícia")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apagar_noticia/<int:id>", methods=["POST"])
@staff_required
def apagar_noticia(id):
    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT categoria FROM noticias WHERE id = %s", (id,))
            noticia = cur.fetchone()
            if not noticia:
                flash("Notícia não encontrada.", "danger")
            elif not can_manage_category(session["role"], noticia["categoria"]):
                flash("Não tens permissão para apagar esta notícia.", "danger")
            else:
                cur.execute("DELETE FROM noticias WHERE id = %s", (id,))
                flash("Notícia removida com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("apagar notícia")
    return redirect(url_for("admin_dashboard"))


# ----------------------------- LIVROS ----------------------------------------
@app.route("/admin/adicionar_livro", methods=["POST"])
@roles_required("super_admin", "admin_leitura")
def adicionar_livro():
    titulo = form_text("titulo", max_len=255)
    autor = form_text("autor", max_len=255)
    if not titulo or not autor:
        flash("Título e autor são obrigatórios.", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute(
                "INSERT INTO livros (titulo, autor, status, sinopse, imagem_url) VALUES (%s, %s, %s, %s, %s)",
                (titulo, autor, form_text("status", 50, "destaque"), form_text("sinopse"), form_url("imagem_url")),
            )
        flash("Livro adicionado com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("adicionar livro")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/editar_livro/<int:id>", methods=["POST"])
@roles_required("super_admin", "admin_leitura")
def editar_livro(id):
    titulo = form_text("titulo", max_len=255)
    autor = form_text("autor", max_len=255)
    if not titulo or not autor:
        flash("Título e autor são obrigatórios.", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute(
                "UPDATE livros SET titulo = %s, autor = %s, status = %s, sinopse = %s, imagem_url = %s WHERE id = %s",
                (titulo, autor, form_text("status", 50, "destaque"), form_text("sinopse"), form_url("imagem_url"), id),
            )
        flash("Livro atualizado com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("atualizar livro")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apagar_livro/<int:id>", methods=["POST"])
@roles_required("super_admin", "admin_leitura")
def apagar_livro(id):
    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute("DELETE FROM livros WHERE id = %s", (id,))
        flash("Livro removido dos destaques!", "success")
    except mysql.connector.Error:
        flash_db_error("apagar livro")
    return redirect(url_for("admin_dashboard"))


# ----------------------------- UTILIZADORES (super admin) --------------------
@app.route("/admin/adicionar_user", methods=["POST"])
@roles_required("super_admin")
def admin_adicionar_user():
    nome = form_text("nome_real", max_len=100)
    email = (form_text("email", max_len=50) or "").lower()
    password = request.form.get("password") or ""
    role = form_text("role")

    if not nome or not valid_email(email) or role not in ROLES or len(password) < MIN_PASSWORD_LENGTH:
        flash(f"Dados inválidos (palavra-passe com pelo menos {MIN_PASSWORD_LENGTH} caracteres).", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute(
                "INSERT INTO utilizadores (nome_real, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                (nome, email, generate_password_hash(password), role),
            )
        flash("Utilizador criado com sucesso!", "success")
    except mysql.connector.IntegrityError:
        flash("Erro ao criar: esse e-mail já existe.", "danger")
    except mysql.connector.Error:
        flash_db_error("criar utilizador")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/editar_user/<int:id>", methods=["POST"])
@roles_required("super_admin")
def admin_editar_user(id):
    nome = form_text("nome_real", max_len=100)
    email = (form_text("email", max_len=50) or "").lower()
    role = form_text("role")

    if email and not valid_email(email):
        flash("E-mail inválido.", "danger")
        return redirect(url_for("admin_dashboard"))
    if role and role not in ROLES:
        flash("Papel inválido.", "danger")
        return redirect(url_for("admin_dashboard"))
    if id == session["user_id"] and role and role != "super_admin":
        flash("Não podes retirar o papel de Super Admin à tua própria conta.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT nome_real, email, role FROM utilizadores WHERE id = %s", (id,))
            atual = cur.fetchone()
            if not atual:
                flash("Utilizador não encontrado.", "danger")
                return redirect(url_for("admin_dashboard"))
            # Campos vazios mantêm o valor atual.
            cur.execute(
                "UPDATE utilizadores SET nome_real = %s, email = %s, role = %s WHERE id = %s",
                (nome or atual["nome_real"], email or atual["email"], role or atual["role"], id),
            )
        flash("Utilizador atualizado com sucesso!", "success")
    except mysql.connector.IntegrityError:
        flash("Esse e-mail já está a ser usado por outra conta.", "danger")
    except mysql.connector.Error:
        flash_db_error("atualizar utilizador")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apagar_user/<int:id>", methods=["POST"])
@roles_required("super_admin")
def admin_apagar_user(id):
    if id == session["user_id"]:
        flash("Não podes apagar a tua própria conta de Super Admin!", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute("DELETE FROM utilizadores WHERE id = %s", (id,))
        flash("Utilizador removido com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("apagar utilizador")
    return redirect(url_for("admin_dashboard"))


# ----------------------------- CATEGORIAS (super admin) ----------------------
@app.route("/admin/adicionar_categoria", methods=["POST"])
@roles_required("super_admin")
def adicionar_categoria():
    nome = (form_text("nome_categoria", max_len=100) or "").lower()
    if not nome:
        flash("O nome da categoria não pode estar vazio.", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_cursor(dictionary=False) as (_, cur):
            cur.execute(
                "INSERT INTO categorias (nome, descricao) VALUES (%s, %s)",
                (nome, form_text("descricao_categoria")),
            )
        flash(f'Nova categoria "{nome}" criada com sucesso!', "success")
    except mysql.connector.IntegrityError:
        flash("Essa categoria já se encontra registada.", "danger")
    except mysql.connector.Error:
        flash_db_error("criar categoria")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/editar_categoria/<int:id>", methods=["POST"])
@roles_required("super_admin")
def editar_categoria(id):
    nome = (form_text("nome_categoria", max_len=100) or "").lower()
    if not nome:
        flash("O nome da categoria não pode estar vazio.", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT nome FROM categorias WHERE id = %s", (id,))
            atual = cur.fetchone()
            if not atual:
                flash("Categoria não encontrada.", "danger")
                return redirect(url_for("admin_dashboard"))
            if atual["nome"] in CORE_CATEGORIES and nome != atual["nome"]:
                flash("As categorias base (leitura, teatro, externo) não podem ser renomeadas.", "danger")
                return redirect(url_for("admin_dashboard"))

            cur.execute(
                "UPDATE categorias SET nome = %s, descricao = %s WHERE id = %s",
                (nome, form_text("descricao_categoria"), id),
            )
            # Mantém a coerência: conteúdos que usavam o nome antigo passam a usar o novo.
            if nome != atual["nome"]:
                cur.execute("UPDATE eventos SET categoria = %s WHERE categoria = %s", (nome, atual["nome"]))
                cur.execute("UPDATE noticias SET categoria = %s WHERE categoria = %s", (nome, atual["nome"]))
        flash("Categoria atualizada com sucesso!", "success")
    except mysql.connector.IntegrityError:
        flash("Já existe uma categoria com esse nome.", "danger")
    except mysql.connector.Error:
        flash_db_error("atualizar categoria")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/apagar_categoria/<int:id>", methods=["POST"])
@roles_required("super_admin")
def apagar_categoria(id):
    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT nome FROM categorias WHERE id = %s", (id,))
            categoria = cur.fetchone()
            if not categoria:
                flash("Categoria não encontrada.", "danger")
                return redirect(url_for("admin_dashboard"))
            if categoria["nome"] in CORE_CATEGORIES:
                flash("As categorias base (leitura, teatro, externo) não podem ser removidas.", "danger")
                return redirect(url_for("admin_dashboard"))

            cur.execute(
                "SELECT (SELECT COUNT(*) FROM eventos WHERE categoria = %s) + "
                "(SELECT COUNT(*) FROM noticias WHERE categoria = %s) AS total",
                (categoria["nome"], categoria["nome"]),
            )
            if cur.fetchone()["total"] > 0:
                flash("Não é possível remover: existem eventos ou notícias nesta categoria.", "danger")
                return redirect(url_for("admin_dashboard"))

            cur.execute("DELETE FROM categorias WHERE id = %s", (id,))
        flash("Categoria removida com sucesso!", "success")
    except mysql.connector.Error:
        flash_db_error("apagar categoria")
    return redirect(url_for("admin_dashboard"))


# =============================================================================
# TRATAMENTO DE ERROS
# =============================================================================
@app.errorhandler(CSRFError)
def handle_csrf_error(_error):
    flash("A sessão expirou ou o pedido é inválido. Tenta novamente.", "danger")
    return safe_back()


@app.errorhandler(404)
def not_found(_error):
    return render_template("erro.html", codigo=404, mensagem="Página não encontrada."), 404


@app.errorhandler(500)
def server_error(_error):
    return render_template("erro.html", codigo=500, mensagem="Ocorreu um erro interno. Tenta novamente."), 500


@app.errorhandler(mysql.connector.Error)
def database_unavailable(error):
    app.logger.error("Base de dados indisponível: %s", error)
    return render_template("erro.html", codigo=503, mensagem="Serviço temporariamente indisponível."), 503


if __name__ == "__main__":
    # Modo debug apenas se pedido explicitamente (nunca em produção).
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
