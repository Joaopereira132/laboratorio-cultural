-- =============================================================================
-- Dados de DEMONSTRAÇÃO (fictícios). Executar depois de schema.sql:
--   mysql -u root -p lab_cultural < database/seed.sql
-- Contas de demonstração (palavra-passe de todas: Demo@2026):
--   super@exemplo.pt (super_admin) | leitura@exemplo.pt (admin_leitura)
--   teatro@exemplo.pt (admin_teatro) | aluno@exemplo.pt (aluno)
-- NÃO usar estas contas em produção. As datas dos eventos são relativas à data de execução.
-- =============================================================================
USE lab_cultural;
SET NAMES utf8mb4;

INSERT INTO utilizadores (id, nome_real, email, password_hash, role) VALUES
(1, 'Super Administrador', 'super@exemplo.pt', 'scrypt:32768:8:1$NTlrfd4fkEcAFzUM$464e79627caa0970b17019115c5505fe6eac8cd4034ac874b47ade5883d461fa3b164eb287380e275f001b4c4931f4283fde94dd9a6fd951eead548c9dacce84', 'super_admin'),
(2, 'Diretor do Clube de Leitura', 'leitura@exemplo.pt', 'scrypt:32768:8:1$NTlrfd4fkEcAFzUM$464e79627caa0970b17019115c5505fe6eac8cd4034ac874b47ade5883d461fa3b164eb287380e275f001b4c4931f4283fde94dd9a6fd951eead548c9dacce84', 'admin_leitura'),
(3, 'Diretora do Clube de Teatro', 'teatro@exemplo.pt', 'scrypt:32768:8:1$NTlrfd4fkEcAFzUM$464e79627caa0970b17019115c5505fe6eac8cd4034ac874b47ade5883d461fa3b164eb287380e275f001b4c4931f4283fde94dd9a6fd951eead548c9dacce84', 'admin_teatro'),
(4, 'Aluno de Teste', 'aluno@exemplo.pt', 'scrypt:32768:8:1$NTlrfd4fkEcAFzUM$464e79627caa0970b17019115c5505fe6eac8cd4034ac874b47ade5883d461fa3b164eb287380e275f001b4c4931f4283fde94dd9a6fd951eead548c9dacce84', 'aluno');

INSERT INTO categorias (nome, descricao) VALUES
('leitura', 'Atividades e sessões do Clube de Leitura'),
('teatro', 'Ensaios e espetáculos do Clube de Teatro'),
('externo', 'Eventos, roteiros e conferências fora do campus'),
('geral', 'Avisos e notícias gerais do laboratório');

INSERT INTO eventos (titulo, descricao, data_evento, local, distrito, cidade, categoria, status, vagas_totais, vagas_ocupadas, autor_id, imagem_url, tipo_evento) VALUES
('Workshop de Fotografia Noturna', 'Exploração técnica de longa exposição urbana.', TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 5 DAY), '20:00:00'), 'Baixa do Porto', 'Porto', 'Porto', 'externo', 'agendado', 20, 0, 1, 'https://images.unsplash.com/photo-1478720568477-152d9b164e26?q=80&w=800', 'Workshop'),
('Concerto de Jazz no Auditório', 'Uma noite dedicada ao jazz clássico e contemporâneo.', TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 9 DAY), '21:00:00'), 'Auditório Central', 'Aveiro', 'Aveiro', 'teatro', 'agendado', 100, 0, 1, 'https://images.unsplash.com/photo-1511192336575-5a79af67a629?q=80&w=800', 'Espetáculo'),
('Feira do Livro de Lisboa', 'Visita guiada às principais bancas e lançamentos.', TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 14 DAY), '10:00:00'), 'Parque Eduardo VII', 'Lisboa', 'Lisboa', 'externo', 'agendado', 50, 0, 1, 'https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?q=80&w=800', 'Visita'),
('Ensaio Aberto: Auto da Barca', 'Ensaio geral aberto à comunidade académica.', TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 3 DAY), '19:00:00'), 'Sala de Ensaios', 'Porto', 'Vila Nova de Gaia', 'teatro', 'agendado', 30, 0, 1, 'https://images.unsplash.com/photo-1507676184212-d03ab07a01bf?q=80&w=800', 'Ensaio'),
('Tertúlia: Memorial do Convento', 'Sessão de análise profunda à obra de José Saramago.', TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 2 DAY), '18:30:00'), 'Biblioteca do Campus', 'Porto', 'Vila Nova de Gaia', 'leitura', 'agendado', 30, 0, 1, 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?q=80&w=800', 'Tertúlia'),
('Encontro: Poesia Portuguesa', 'Leitura comentada de poemas de Fernando Pessoa e Sophia de Mello Breyner.', TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 12 DAY), '17:00:00'), 'Sala de Estudos', 'Lisboa', 'Lisboa', 'leitura', 'agendado', 25, 0, 1, 'https://images.unsplash.com/photo-1532012193857-094b76c8c83a?q=80&w=800', 'Encontro'),
('Clube de Leitura: Grandes Clássicos', 'Discussão informal sobre Os Maias.', TIMESTAMP(DATE_ADD(CURDATE(), INTERVAL 20 DAY), '16:00:00'), 'Auditório Sul', 'Porto', 'Porto', 'leitura', 'agendado', 40, 0, 1, 'https://images.unsplash.com/photo-1495446815901-a7297e633e8d?q=80&w=800', 'Clube de Leitura');

INSERT INTO livros (titulo, autor, status, sinopse, imagem_url) VALUES
('Memorial do Convento', 'José Saramago', 'destaque', NULL, NULL),
('Os Maias', 'Eça de Queirós', 'destaque', NULL, NULL),
('O Principezinho', 'Antoine de Saint-Exupéry', 'destaque', NULL, NULL),
('A Sibila', 'Agustina Bessa-Luís', 'destaque', NULL, NULL),
('Mensagem', 'Fernando Pessoa', 'destaque', NULL, NULL);

INSERT INTO noticias (titulo, resumo, conteudo, categoria, imagem_url, autor_id, status, data_publicacao) VALUES
('Clube de Leitura: Análise de Saramago', 'Uma sessão intensa sobre Memorial do Convento.', 'Junta-te a nós para a nossa próxima sessão de debate literário. Vamos explorar os temas profundos de "Memorial do Convento" e o estilo único de José Saramago. Tragam as vossas opiniões e participem nesta tertúlia.', 'leitura', 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?q=80&w=800', 1, 'publicado', NOW() - INTERVAL 2 DAY),
('Bastidores: A construção da cenografia', 'Como estamos a dar vida ao Auto da Barca do Inferno.', 'Damos um salto aos bastidores para ver como a equipa de cenografia está a construir os cenários para a peça. O esforço da equipa técnica está a ser incrível e o resultado final no Auditório será memorável.', 'teatro', 'https://images.unsplash.com/photo-1460723237483-7a6dc9d0b212?q=80&w=800', 1, 'publicado', NOW() - INTERVAL 4 DAY),
('Nova Parceria com a Biblioteca Municipal', 'Acesso privilegiado ao catálogo digital para todos os alunos.', 'Temos o prazer de anunciar que os membros do nosso Lab Cultural agora têm acesso prioritário ao catálogo digital da Biblioteca Municipal. Consulta o protocolo na secretaria para saber como ativar a tua conta.', 'geral', 'https://images.unsplash.com/photo-1568667256549-094345857637?q=80&w=800', 1, 'publicado', NOW() - INTERVAL 6 DAY),
('Teatro: Call para novos atores', 'O Clube de Teatro aceita novas audições.', 'Estás pronto para subir ao palco? As audições para a próxima produção do clube estão abertas a alunos de todos os cursos. Não precisas de experiência prévia, apenas vontade de aprender!', 'teatro', 'https://images.unsplash.com/photo-1507676184212-d03ab07a01bf?q=80&w=800', 1, 'publicado', NOW() - INTERVAL 8 DAY);
