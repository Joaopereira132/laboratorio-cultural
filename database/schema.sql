-- =============================================================================
-- Laboratório Cultural - esquema da base de dados (MySQL 8 / MariaDB 10.4+)
-- Uso:  mysql -u root -p < database/schema.sql   (cria a base "lab_cultural")
-- =============================================================================
CREATE DATABASE IF NOT EXISTS lab_cultural CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE lab_cultural;

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS inscricoes, membros_clube_leitura, membros_clube_teatro,
                     noticias, eventos, livros, categorias, utilizadores;
SET FOREIGN_KEY_CHECKS = 1;

-- Utilizadores e perfis (RBAC): aluno, admin_leitura, admin_teatro, super_admin
CREATE TABLE utilizadores (
  id            INT AUTO_INCREMENT PRIMARY KEY,
  nome_real     VARCHAR(100) NOT NULL,
  email         VARCHAR(50)  NOT NULL,
  password_hash VARCHAR(255) NOT NULL,                      -- hash scrypt (werkzeug), nunca texto limpo
  role          ENUM('super_admin','admin_leitura','admin_teatro','aluno') NOT NULL DEFAULT 'aluno',
  ativo         TINYINT(1)   NOT NULL DEFAULT 1,
  data_criacao  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_utilizadores_email (email)
) ENGINE=InnoDB;

-- Categorias dinâmicas (geridas pelo super admin)
CREATE TABLE categorias (
  id        INT AUTO_INCREMENT PRIMARY KEY,
  nome      VARCHAR(100) NOT NULL,
  descricao TEXT NULL,
  UNIQUE KEY uq_categorias_nome (nome)
) ENGINE=InnoDB;

-- Eventos (a lotação é protegida por CHECK + UPDATE atómico na aplicação)
CREATE TABLE eventos (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  titulo         VARCHAR(100) NOT NULL,
  descricao      TEXT NULL,
  data_evento    DATETIME NULL,
  local          VARCHAR(100) NULL,
  distrito       VARCHAR(100) NULL,
  cidade         VARCHAR(100) NULL DEFAULT 'Gaia',
  categoria      VARCHAR(100) NOT NULL,
  status         ENUM('agendado','realizado','cancelado') NOT NULL DEFAULT 'agendado',
  vagas_totais   INT NOT NULL DEFAULT 0,
  vagas_ocupadas INT NOT NULL DEFAULT 0,
  autor_id       INT NULL,
  imagem_url     VARCHAR(255) NULL,
  tipo_evento    VARCHAR(50) NULL DEFAULT 'Outro',
  CONSTRAINT chk_eventos_vagas CHECK (vagas_ocupadas >= 0 AND vagas_ocupadas <= vagas_totais),
  KEY idx_eventos_listagem (categoria, status, data_evento),
  CONSTRAINT fk_eventos_autor FOREIGN KEY (autor_id) REFERENCES utilizadores (id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Inscrições (utilizadores registados OU convidados com e-mail)
CREATE TABLE inscricoes (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  evento_id       INT NOT NULL,
  user_id         INT NULL,
  nome_convidado  VARCHAR(150) NULL,
  email_convidado VARCHAR(150) NULL,
  data_inscricao  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  -- Impedem inscrições duplicadas mesmo com pedidos simultâneos (NULL não colide):
  UNIQUE KEY uq_inscricao_utilizador (evento_id, user_id),
  UNIQUE KEY uq_inscricao_convidado (evento_id, email_convidado),
  CONSTRAINT chk_inscricao_origem CHECK (user_id IS NOT NULL OR email_convidado IS NOT NULL),
  CONSTRAINT fk_inscricoes_evento FOREIGN KEY (evento_id) REFERENCES eventos (id) ON DELETE CASCADE,
  CONSTRAINT fk_inscricoes_user   FOREIGN KEY (user_id)   REFERENCES utilizadores (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE livros (
  id           INT AUTO_INCREMENT PRIMARY KEY,
  titulo       VARCHAR(255) NOT NULL,
  autor        VARCHAR(255) NOT NULL,
  status       VARCHAR(50)  NOT NULL DEFAULT 'destaque',
  data_criacao TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  sinopse      TEXT NULL,
  imagem_url   VARCHAR(255) NULL
) ENGINE=InnoDB;

CREATE TABLE noticias (
  id              INT AUTO_INCREMENT PRIMARY KEY,
  titulo          VARCHAR(150) NOT NULL,
  resumo          VARCHAR(255) NULL,
  conteudo        TEXT NULL,
  categoria       VARCHAR(100) NOT NULL,
  imagem_url      VARCHAR(255) NULL,
  autor_id        INT NULL,
  status          ENUM('rascunho','publicado') NOT NULL DEFAULT 'publicado',
  data_publicacao TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_noticias_listagem (categoria, status, data_publicacao),
  CONSTRAINT fk_noticias_autor FOREIGN KEY (autor_id) REFERENCES utilizadores (id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Pertença aos clubes (um registo por utilizador)
CREATE TABLE membros_clube_leitura (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  user_id        INT NOT NULL,
  data_inscricao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_membro_leitura (user_id),
  CONSTRAINT fk_membro_leitura FOREIGN KEY (user_id) REFERENCES utilizadores (id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE membros_clube_teatro (
  id             INT AUTO_INCREMENT PRIMARY KEY,
  user_id        INT NOT NULL,
  data_inscricao DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_membro_teatro (user_id),
  CONSTRAINT fk_membro_teatro FOREIGN KEY (user_id) REFERENCES utilizadores (id) ON DELETE CASCADE
) ENGINE=InnoDB;
