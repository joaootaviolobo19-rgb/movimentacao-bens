import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import app as aplicacao
import email_sender
import enviar_alertas
import permissoes


class TestRegressoes(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.caminho_dados = Path(self.tempdir.name)
        self.arquivo_ferias = self.caminho_dados / "ferias.json"
        self.patches = [
            patch.object(aplicacao, "ARQ_FER", str(self.arquivo_ferias)),
            patch.object(
                aplicacao.mod_usuarios,
                "carregar_usuarios",
                return_value=[{
                    "usuario": "teste",
                    "nome": "Conta de teste",
                    "tipo": "admin",
                }],
            ),
            patch.object(aplicacao.permissoes, "tem_permissao", return_value=True),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        aplicacao.app.config.update(TESTING=True)
        self.client = aplicacao.app.test_client()

    def _autenticar(self):
        with self.client.session_transaction() as sessao:
            sessao["usuario"] = "teste"
            sessao["nome"] = "Conta de teste"
            sessao["tipo"] = "admin"

    def test_atualizacao_preserva_status_legado_de_ferias(self):
        registro = {
            "nome": "Pessoa de teste",
            "inicio": "2030-05-01",
            "fim": "2030-05-10",
            "status": "Férias iniciada",
            "obs": "",
        }
        self.arquivo_ferias.write_text(
            json.dumps([registro], ensure_ascii=False), encoding="utf-8"
        )
        self._autenticar()

        resposta = self.client.post(
            "/ferias/salvar",
            json={
                "idx": 0,
                "nome": registro["nome"],
                "inicio": registro["inicio"],
                "fim": registro["fim"],
                "obs": "Observação atualizada",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        salvo = json.loads(self.arquivo_ferias.read_text(encoding="utf-8"))
        self.assertEqual(salvo[0]["status"], "Férias iniciada")
        self.assertEqual(salvo[0]["obs"], "Observação atualizada")

    def test_status_legado_de_ferias_pode_ser_recebido(self):
        self._autenticar()

        resposta = self.client.post(
            "/ferias/salvar",
            json={
                "nome": "Pessoa de teste",
                "inicio": "2030-05-01",
                "fim": "2030-05-10",
                "status": "Férias iniciada",
                "obs": "",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        salvo = json.loads(self.arquivo_ferias.read_text(encoding="utf-8"))
        self.assertEqual(salvo[0]["status"], "Férias iniciada")

    def test_todas_as_rotas_de_aplicacao_tem_recurso_configurado(self):
        excecoes = {
            "static",
            "login",
            "logout",
            "api_rodar_alertas_cron",
        }
        sem_recurso = {
            regra.endpoint
            for regra in aplicacao.app.url_map.iter_rules()
            if regra.endpoint not in set(aplicacao.RECURSO_POR_ENDPOINT) | excecoes
        }

        self.assertEqual(sem_recurso, set())

    def test_perfil_de_consulta_nao_pode_exportar_csv(self):
        with patch.object(
            aplicacao.mod_usuarios,
            "carregar_usuarios",
            return_value=[{
                "usuario": "teste",
                "nome": "Conta de teste",
                "tipo": "consulta",
            }],
        ), patch.object(
            aplicacao.permissoes,
            "tem_permissao",
            side_effect=lambda perfil_id, permissao: (
                permissao == "bens.ver" if perfil_id == "consulta" else False
            ),
        ):
            with self.client.session_transaction() as sessao:
                sessao["usuario"] = "teste"
                sessao["nome"] = "Conta de teste"
                sessao["tipo"] = "consulta"

            resposta = self.client.get("/bens/exportar.csv")

        self.assertEqual(resposta.status_code, 403)

    def test_endpoint_do_cron_executa_rotina_com_token_configurado(self):
        token = "cron-test-secret"
        with (
            patch.dict(os.environ, {"ALERTAS_CRON_TOKEN": token}),
            patch("enviar_alertas.main") as executar,
        ):
            resposta = self.client.get(f"/api/rodar_alertas/{token}")

        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.get_json()["ok"])
        executar.assert_called_once_with()

    def test_endpoint_do_cron_rejeita_token_incorreto(self):
        with (
            patch.dict(os.environ, {"ALERTAS_CRON_TOKEN": "cron-test-secret"}),
            patch("enviar_alertas.main") as executar,
        ):
            resposta = self.client.get("/api/rodar_alertas/token-incorreto")

        self.assertEqual(resposta.status_code, 403)
        executar.assert_not_called()

    def test_endpoint_do_cron_informa_quando_token_nao_esta_configurado(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(aplicacao, "DADOS", str(self.caminho_dados)),
        ):
            resposta = self.client.get("/api/rodar_alertas/token-qualquer")

        self.assertEqual(resposta.status_code, 503)

    def test_indicacao_de_ferias_fica_ao_lado_do_nome_na_central(self):
        with (
            patch.object(
                aplicacao,
                "_pessoas_agrupadas",
                return_value=[{
                    "nome": "Pessoa de teste",
                    "cargo": "Analista",
                    "departamento": "TI",
                    "ramal": "3001",
                    "em_ferias": True,
                }],
            ),
            patch.object(aplicacao, "ferias_em_andamento_lista", return_value=[]),
        ):
            self._autenticar()
            resposta = self.client.get("/recepcao")

        self.assertEqual(resposta.status_code, 200)
        html = resposta.get_data(as_text=True)
        self.assertIn("Pessoa de teste", html)
        self.assertIn("Em férias", html)
        self.assertNotIn("<th style=\"width:70px; text-align:center;\">Férias</th>", html)

    def test_ramais_para_impressao_priorizam_diretorias_e_areas_de_atendimento(self):
        bens = [
            {"ramal": "3001", "responsavel": "Pessoa TI", "departamento": "TI"},
            {"ramal": "3002", "responsavel": "Pessoa Sala", "departamento": "Sala de Reunião"},
            {"ramal": "3003", "responsavel": "Pessoa Portaria", "departamento": "Portaria"},
            {"ramal": "3004", "responsavel": "Pessoa Copa", "departamento": "Copa"},
            {"ramal": "3005", "responsavel": "Pessoa Recepção", "departamento": "Recepção"},
            {"ramal": "3006", "responsavel": "Pessoa Diretoria", "departamento": "Diretor Executivo"},
            {"ramal": "3007", "responsavel": "Pessoa Administrativa", "departamento": "Diretor Administrativo"},
            {"ramal": "3008", "responsavel": "Pessoa Secretaria", "departamento": "Secretaria de Diretoria"},
        ]
        with (
            patch.object(aplicacao, "load_bens", return_value=bens),
            patch.object(aplicacao, "ferias_ativas_chaves", return_value=set()),
        ):
            self._autenticar()
            resposta = self.client.get("/ramais")

        self.assertEqual(resposta.status_code, 200)
        html = resposta.get_data(as_text=True)
        html = html[html.index('<article class="impressao-ramais"'):]
        posicoes = [
            html.index(f"<h2>{departamento}</h2>")
            for departamento in (
                "Diretor Executivo",
                "Diretor Administrativo",
                "Secretaria de Diretoria",
                "Recepção",
                "Copa",
                "Portaria",
                "Sala de Reunião",
                "TI",
            )
        ]
        self.assertEqual(posicoes, sorted(posicoes))

    def test_edicao_de_bens_nao_concede_permissao_de_transferencia(self):
        with patch.object(
            aplicacao.mod_usuarios,
            "carregar_usuarios",
            return_value=[{
                "usuario": "teste",
                "nome": "Conta de teste",
                "tipo": "inventario",
            }],
        ), patch.object(
            aplicacao.permissoes,
            "tem_permissao",
            side_effect=lambda perfil_id, permissao: (
                permissao in {"bens.ver", "bens.editar"}
                if perfil_id == "inventario" else False
            ),
        ):
            with self.client.session_transaction() as sessao:
                sessao["usuario"] = "teste"
                sessao["nome"] = "Conta de teste"
                sessao["tipo"] = "inventario"

            resposta = self.client.post("/bens/transferir", json={})

        self.assertEqual(resposta.status_code, 403)


class TestPermissoes(unittest.TestCase):
    def test_central_so_e_exibida_quando_concedida_explicitamente(self):
        with tempfile.TemporaryDirectory() as temporario:
            with (
                patch.object(permissoes, "DADOS", temporario),
                patch.object(
                    permissoes, "ARQ_PERFIS", str(Path(temporario) / "perfis.json")
                ),
            ):
                self.assertFalse(permissoes.tem_permissao("admin", "recepcao.ver"))
                self.assertTrue(permissoes.tem_permissao("recepcao", "recepcao.ver"))
                salvo, mensagem = permissoes.salvar_perfil(
                    "", "Atendimento personalizado", ["recepcao.ver"]
                )

                self.assertTrue(salvo, mensagem)
                self.assertTrue(
                    permissoes.tem_permissao(
                        "atendimento-personalizado", "recepcao.ver"
                    )
                )

    def test_administrador_sem_concessao_nao_abre_a_central(self):
        with tempfile.TemporaryDirectory() as temporario:
            caminho_perfis = Path(temporario) / "perfis.json"
            metodo_permissao = permissoes.tem_permissao
            with (
                patch.object(permissoes, "DADOS", temporario),
                patch.object(permissoes, "ARQ_PERFIS", str(caminho_perfis)),
                patch.object(permissoes, "tem_permissao", side_effect=metodo_permissao),
                patch.object(
                    aplicacao.mod_usuarios,
                    "carregar_usuarios",
                    return_value=[{
                        "usuario": "ti",
                        "nome": "Administrador TI",
                        "tipo": "admin",
                    }],
                ),
            ):
                cliente = aplicacao.app.test_client()
                with cliente.session_transaction() as sessao:
                    sessao["usuario"] = "ti"
                    sessao["nome"] = "Administrador TI"
                    sessao["tipo"] = "admin"

                resposta = cliente.get("/recepcao")

        self.assertEqual(resposta.status_code, 403)


    def test_perfil_de_consulta_nao_recebe_permissao_de_edicao(self):
        with tempfile.TemporaryDirectory() as temporario:
            with (
                patch.object(permissoes, "DADOS", temporario),
                patch.object(permissoes, "ARQ_PERFIS", str(Path(temporario) / "perfis.json")),
            ):
                salvo, mensagem = permissoes.salvar_perfil(
                    "", "Consulta", ["bens.ver"]
                )

                self.assertTrue(salvo, mensagem)
                self.assertTrue(permissoes.tem_permissao("consulta", "bens.ver"))
                self.assertFalse(permissoes.tem_permissao("consulta", "bens.editar"))

    def test_perfis_personalizados_nao_podem_exportar_ramais_ou_movimentar_bens(self):
        with tempfile.TemporaryDirectory() as temporario:
            arquivo_perfis = Path(temporario) / "perfis.json"
            arquivo_perfis.write_text(
                json.dumps([{
                    "id": "legado",
                    "nome": "Perfil legado",
                    "permissoes": [
                        "ramais.exportar",
                        "movimentacoes.editar",
                        "bens.ver",
                        "bens.editar",
                    ],
                }]),
                encoding="utf-8",
            )
            with (
                patch.object(permissoes, "DADOS", temporario),
                patch.object(permissoes, "ARQ_PERFIS", str(arquivo_perfis)),
            ):
                self.assertTrue(permissoes.tem_permissao("legado", "bens.editar"))
                self.assertFalse(permissoes.tem_permissao("legado", "ramais.exportar"))
                self.assertFalse(
                    permissoes.tem_permissao("legado", "movimentacoes.editar")
                )

                salvo, _ = permissoes.salvar_perfil(
                    "", "Novo", ["ramais.ver", "ramais.exportar"]
                )
                self.assertFalse(salvo)
                salvo, _ = permissoes.salvar_perfil(
                    "", "Novo", ["movimentacoes.ver", "movimentacoes.editar"]
                )
                self.assertFalse(salvo)


class TestAlertasFerias(unittest.TestCase):
    def test_envia_alertas_de_inicio_hoje_e_retorno_amanha(self):
        class Hoje(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 7, 8)

        registros = [
            {
                "nome": "Pessoa & teste",
                "inicio": "2026-10-07",
                "fim": "2026-10-17",
                "status": "Férias iniciada",
            },
            {
                "nome": "Pessoa de retorno",
                "inicio": "2026-10-01",
                "fim": "2026-10-08",
                "status": "Férias iniciada",
            },
        ]
        configuracao = {
            "destinatarios_ferias": ["ti@example.com"],
            "assunto_ferias": "Retorno de férias",
        }
        with (
            patch.object(enviar_alertas, "datetime", Hoje),
            patch.object(enviar_alertas, "_load_json", return_value=registros),
            patch.object(
                enviar_alertas.email_sender,
                "enviar_email",
                return_value=(True, "enviado"),
            ) as enviar,
        ):
            enviar_alertas.enviar_inicio_ferias(configuracao)
            enviar_alertas.enviar_alertas_ferias(configuracao)

        self.assertEqual(enviar.call_count, 2)
        self.assertEqual(enviar.call_args_list[0].kwargs["tipo"], "ferias_inicio")
        self.assertEqual(enviar.call_args_list[1].kwargs["tipo"], "ferias")
        self.assertIn("&amp;", enviar.call_args_list[0].args[2])
        self.assertIn("08/10/2026", enviar.call_args_list[1].args[2])


class TestMigracaoConfiguracaoEmail(unittest.TestCase):
    def test_configuracao_smtp_legada_continua_disponivel_na_transicao(self):
        with tempfile.TemporaryDirectory() as temporario:
            config_antiga = Path(temporario) / "config_email.json"
            config_antiga.write_text(
                json.dumps({
                    "ativo": True,
                    "smtp_user": "smtp@example.com",
                    "smtp_pass": "senha-de-teste",
                    "destinatarios_ferias": ["ti@example.com"],
                }),
                encoding="utf-8",
            )
            with (
                patch.object(
                    email_sender, "ARQ_CONFIG",
                    str(Path(temporario) / "config_email.local.json"),
                ),
                patch.object(email_sender, "ARQ_CONFIG_LEGADO", str(config_antiga)),
                patch.dict(os.environ, {}, clear=True),
            ):
                configuracao = email_sender.carregar_config()

        self.assertTrue(configuracao["ativo"])
        self.assertEqual(configuracao["smtp_user"], "smtp@example.com")
        self.assertEqual(configuracao["destinatarios_ferias"], ["ti@example.com"])


if __name__ == "__main__":
    unittest.main()
