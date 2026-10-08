import re
from datetime import date
from pathlib import Path

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse

from .models import Estudante, Monitor, Quarto, Vistoria, SolicitacaoReparo, Cronograma, Tarefa


class VistoriaFlowTests(TestCase):
    def setUp(self):
        self.quarto = Quarto.objects.create(numero='101', bloco='A')
        self.u_est = User.objects.create_user('aluno1', password='x')
        self.estudante = Estudante.objects.create(
            user=self.u_est, matricula='123', cpf='12345678901', quarto=self.quarto
        )
        self.u_mon = User.objects.create_user('mon1', password='x')
        self.monitor = Monitor.objects.create(
            user=self.u_mon, siape='1234567', cpf='98765432100', bloco_responsavel='A'
        )
        self.client.force_login(self.u_mon)
        self.url = reverse('detalhes_quarto', args=[self.quarto.id])

    # --- Bug 2: nota (criterios da entrevista com o monitor) ---
    def test_nota_tudo_marcado(self):
        self.client.post(self.url, {
            'chao_lavanderia': '1', 'organizacao_geral': '1', 'janelas_livres': '1',
            'observacoes': 'tudo ok', 'aprovado': 'True',
        })
        self.assertEqual(Vistoria.objects.get().nota, 10)

    def test_nota_parcial_tres_mais_tres(self):
        self.client.post(self.url, {'organizacao_geral': '1', 'janelas_livres': '1', 'aprovado': 'True'})
        self.assertEqual(Vistoria.objects.get().nota, 6)

    def test_nota_apenas_chao_lavanderia(self):
        self.client.post(self.url, {'chao_lavanderia': '1', 'aprovado': 'True'})
        self.assertEqual(Vistoria.objects.get().nota, 4)

    def test_nota_zero_quando_nada_marcado(self):
        self.client.post(self.url, {'aprovado': 'False'})
        self.assertEqual(Vistoria.objects.get().nota, 0)

    def test_nomes_antigos_de_criterio_nao_somam_mais(self):
        """Regressao: HTML e CRITERIOS_VISTORIA precisam ficar em sintonia."""
        self.client.post(self.url, {
            'chao_limpo': '1', 'lixo_retirado': '1',
            'camas_organizadas': '1', 'banheiro_limpo': '1',
            'aprovado': 'True',
        })
        self.assertEqual(Vistoria.objects.get().nota, 0)

    def test_labels_do_monitor_aparecem_no_painel(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('Chão e Lavanderia limpos', html)
        self.assertIn('Organização Geral (Quarto livre de bagunça aparente)', html)
        self.assertIn('Janelas Livres (Sem roupas ou objetos pendurados)', html)
        # criterios antigos sairam
        self.assertNotIn('name="banheiro_limpo"', html)
        self.assertNotIn('name="lixo_retirado"', html)

    # --- Bug 1: status persiste de verdade ---
    def test_aprovar_persiste_status_e_streak(self):
        self.client.post(self.url, {'chao_limpo': '1', 'aprovado': 'True'})
        self.quarto.refresh_from_db()
        self.assertEqual(self.quarto.status, Quarto.STATUS_APROVADO)
        self.assertEqual(self.quarto.streak_dias, 1)

    def test_reprovar_grava_reprovado_nao_pendente(self):
        self.client.post(self.url, {'aprovado': 'False'})
        self.quarto.refresh_from_db()
        self.assertEqual(self.quarto.status, Quarto.STATUS_REPROVADO)
        self.assertEqual(self.quarto.streak_dias, 0)

    # --- Trava de loop ---
    @staticmethod
    def classes_de(html, elemento_id):
        """Classes CSS de um elemento pelo id."""
        import re
        m = re.search(r'id="%s"[^>]*?class="([^"]*)"' % elemento_id, html)
        return m.group(1).split() if m else []

    def test_painel_conclusao_apos_vistoria(self):
        self.client.post(self.url, {'aprovado': 'True'})
        html = self.client.get(self.url).content.decode()
        self.assertIn('Vistoria Concluída', html)
        # botoes ficam ocultos (mas presentes no DOM, p/ o Editar reexibir)
        self.assertIn('hidden', self.classes_de(html, 'area-botoes'))
        self.assertNotIn('hidden', self.classes_de(html, 'area-concluida'))
        self.assertIn('id="btn-editar"', html)

    def test_botoes_visiveis_quando_pendente(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('Aprovar', html)
        self.assertIn('Reprovar', html)
        self.assertNotIn('hidden', self.classes_de(html, 'area-botoes'))
        self.assertIn('hidden', self.classes_de(html, 'area-concluida'))

    def test_modal_nasce_escondido(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('hidden', self.classes_de(html, 'modal-confirmacao'))

    # --- Modal + JS ---
    def test_modal_e_js_presentes(self):
        html = self.client.get(self.url).content.decode()
        import re
        m = re.search(r'id="modal-confirmacao"[^>]*?class="([^"]*)"', html)
        classes = m.group(1).split() if m else []
        self.assertIn('modal-confirmacao', html)
        for classe in ('fixed', 'inset-0', 'items-center', 'justify-center'):
            self.assertIn(classe, classes)
        for fn in ('abrirModal', 'fecharModal', 'confirmarModal', 'editarVistoria'):
            self.assertIn(fn, html)
        self.assertIn('Deseja confirmar a aprovação?', html)
        self.assertIn('Deseja confirmar a reprovação?', html)
        self.assertIn('Recusar', html)
        self.assertIn('Confirmar', html)
        self.assertIn('id="input-aprovado"', html)
        # botoes originais nao podem submeter direto
        self.assertNotIn('type="submit" name="aprovado"', html)

    # --- Bug 4: progresso sem quarto ---
    def test_progresso_sem_quarto_nao_quebra(self):
        self.estudante.quarto = None
        self.estudante.save()
        self.client.force_login(self.u_est)
        self.assertEqual(self.client.get(reverse('progresso')).status_code, 200)

    # --- Bug 3: POST fantasma ---
    def test_get_reportar_nao_cria_chamado(self):
        self.client.force_login(self.u_est)
        self.assertEqual(self.client.get(reverse('reportar_problema')).status_code, 200)
        self.assertEqual(SolicitacaoReparo.objects.count(), 0)

    def test_post_reportar_delega_e_salva(self):
        self.client.force_login(self.u_est)
        r = self.client.post(reverse('reportar_problema'), {
            'titulo': 'Vazamento', 'categoria': 'hidraulica', 'descricao': 'pingando'
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(SolicitacaoReparo.objects.count(), 1)


class ConclusaoTarefaModalTests(TestCase):
    """Modal de confirmacao da conclusao de tarefa no painel do estudante."""

    def setUp(self):
        self.quarto = Quarto.objects.create(numero='202', bloco='B')
        self.u = User.objects.create_user('aluno2', password='x')
        self.estudante = Estudante.objects.create(
            user=self.u, matricula='456', cpf='11122233344', quarto=self.quarto
        )
        self.tarefa = Tarefa.objects.create(
            cronograma=Cronograma.objects.create(
                quarto=self.quarto, data_inicio=date(2026, 10, 1), data_fim=date(2026, 10, 31)
            ),
            estudante_responsavel=self.estudante,
            titulo='Limpar o quarto',
            descricao='Varrer, lavar e organizar',
            data_prazo=date(2026, 10, 10),
            status='Pendente',
        )
        self.client.force_login(self.u)
        self.url_concluir = reverse('concluir_tarefa', args=[self.tarefa.id])

    def html(self):
        return self.client.get(reverse('painel_estudante')).content.decode()

    def test_form_get_apontando_para_concluir_tarefa(self):
        h = self.html()
        self.assertIn('action="%s"' % self.url_concluir, h)
        self.assertIn('id="form-tarefa-%d"' % self.tarefa.id, h)
        self.assertIn('method="GET"', h)

    def test_botao_type_button_com_onclick(self):
        h = self.html()
        self.assertIn('type="button"', h)
        self.assertIn("abrirModalEstudante('form-tarefa-%d')" % self.tarefa.id, h)

    def test_confirm_nativo_removido(self):
        self.assertNotIn('return confirm(', self.html())

    def test_modal_textos_de_contexto_do_aluno(self):
        import re
        h = self.html()
        m = re.search(r'id="modal-estudante"[^>]*?class="([^"]*)"', h)
        classes = m.group(1).split() if m else []
        for classe in ('fixed', 'inset-0', 'items-center', 'justify-center', 'hidden'):
            self.assertIn(classe, classes)
        self.assertIn('Confirmar conclus\u00e3o?', h)
        self.assertIn(
            'Voc\u00ea tem certeza que deseja marcar esta limpeza como conclu\u00edda '
            'e enviar para vistoria?',
            h,
        )
        self.assertIn('Recusar', h)
        self.assertIn('Confirmar', h)

    def test_funcoes_js_presentes(self):
        h = self.html()
        for fn in ('abrirModalEstudante', 'fecharModalEstudante', 'confirmarConclusaoEstudante'):
            self.assertIn(fn, h)
        self.assertIn('.submit()', h)

    def test_modal_nasce_escondido(self):
        import re
        m = re.search(r'id="modal-estudante"[^>]*?class="([^"]*)"', self.html())
        self.assertIn('hidden', m.group(1).split())

    def test_submit_do_form_realmente_conclui_a_tarefa(self):
        """Simula o que o JS faz ao confirmar: submeter o form."""
        self.client.get(self.url_concluir)
        self.tarefa.refresh_from_db()
        self.assertEqual(self.tarefa.status, 'Conclu\u00edda')

    def test_tarefa_concluida_nao_mostra_botao_nem_form(self):
        self.tarefa.status = 'Concluída'
        self.tarefa.save()
        h = self.html()
        self.assertNotIn('id="form-tarefa-%d"' % self.tarefa.id, h)


class VerificarReparoTests(TestCase):
    """Botao 'Marcar como Verificado' no painel do monitor."""

    def setUp(self):
        self.quarto = Quarto.objects.create(numero='404', bloco='D')
        self.u_est = User.objects.create_user('aluno3', password='x')
        self.estudante = Estudante.objects.create(
            user=self.u_est, matricula='777', cpf='22233344455', quarto=self.quarto
        )
        self.u_mon = User.objects.create_user('mon2', password='x')
        Monitor.objects.create(
            user=self.u_mon, siape='7654321', cpf='44455566677', bloco_responsavel='D'
        )
        self.reparo = SolicitacaoReparo.objects.create(
            estudante=self.estudante,
            titulo='Vazamento no banheiro',
            categoria='hidraulica',
            descricao='Torneira pingando desde segunda',
        )
        self.url_verificar = reverse('verificar_reparo', args=[self.reparo.id])

    def html_do_monitor(self):
        self.client.force_login(self.u_mon)
        return self.client.get(reverse('painel_monitor')).content.decode()

    def test_chamado_aparece_no_painel_do_monitor(self):
        html = self.html_do_monitor()
        self.assertIn('Chamados de Infraestrutura', html)
        self.assertIn('Vazamento no banheiro', html)
        self.assertIn('Marcar como Verificado', html)

    def test_botao_aponta_para_url_correta(self):
        self.assertIn('action="%s"' % self.url_verificar, self.html_do_monitor())

    def test_post_marca_como_verificado_no_banco(self):
        self.client.force_login(self.u_mon)
        r = self.client.post(self.url_verificar)
        self.assertEqual(r.status_code, 302)
        self.reparo.refresh_from_db()
        self.assertEqual(self.reparo.status, 'Verificado')

    def test_depois_de_verificar_botao_some_e_badge_muda(self):
        self.client.force_login(self.u_mon)
        self.client.post(self.url_verificar)
        html = self.client.get(reverse('painel_monitor')).content.decode()
        self.assertNotIn('Marcar como Verificado', html)
        self.assertIn('fa-check-double', html)

    def test_get_nao_altera_nada(self):
        self.client.force_login(self.u_mon)
        self.client.get(self.url_verificar)
        self.reparo.refresh_from_db()
        self.assertEqual(self.reparo.status, 'Em Aberto')

    def test_estudante_nao_pode_verificar(self):
        self.client.force_login(self.u_est)
        self.client.post(self.url_verificar)
        self.reparo.refresh_from_db()
        self.assertEqual(self.reparo.status, 'Em Aberto')

    def test_visitante_redirecionado_para_login(self):
        r = self.client.post(self.url_verificar)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login/', r.url)

    def test_status_padrao_ainda_em_aberto(self):
        self.assertEqual(self.reparo.status, 'Em Aberto')


class StreakCardTests(TestCase):
    """Contador numerico do card 'Streak de Limpeza' no painel do estudante."""

    def setUp(self):
        self.quarto = Quarto.objects.create(numero='606', bloco='F')
        self.u = User.objects.create_user('aluno_streak', password='x')
        self.estudante = Estudante.objects.create(
            user=self.u, matricula='888', cpf='66677788899', quarto=self.quarto
        )
        self.client.force_login(self.u)

    def html(self):
        return self.client.get(reverse('painel_estudante')).content.decode()

    @staticmethod
    def numero_streak(html):
        """Extrai os digitos renderizados no <span class="text-5xl font-black">."""
        import re
        m = re.search(r'font-black">\s*(\d+)\s*<', html)
        return m.group(1) if m else None

    def test_streak_zero_saida_com_dois_digitos(self):
        self.assertEqual(self.numero_streak(self.html()), '00')

    def test_streak_cinco_saida_05(self):
        self.quarto.streak_dias = 5
        self.quarto.save()
        self.assertEqual(self.numero_streak(self.html()), '05')

    def test_streak_dez_nao_vira_010(self):
        self.quarto.streak_dias = 10
        self.quarto.save()
        self.assertEqual(self.numero_streak(self.html()), '10')

    def test_streak_cem_nao_e_truncado(self):
        self.quarto.streak_dias = 100
        self.quarto.save()
        self.assertEqual(self.numero_streak(self.html()), '100')

    def test_streak_alto_acende_fogueira(self):
        self.quarto.streak_dias = 10
        self.quarto.save()
        h = self.html()
        self.assertIn('Fogueira acesa!', h)
        self.assertNotIn('Mantenha 3 vistorias', h)

    def test_streak_baixo_mantem_card_azul(self):
        self.quarto.streak_dias = 2
        self.quarto.save()
        h = self.html()
        self.assertIn('Mantenha 3 vistorias', h)
        self.assertIn('bg-blue-600', h)

    def test_estudante_sem_quarto_nao_quebra(self):
        self.estudante.quarto = None
        self.estudante.save()
        r = self.client.get(reverse('painel_estudante'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.numero_streak(r.content.decode()), '00')

    def test_model_nao_tem_campo_streak_so_streak_dias(self):
        """Regressao: o template apontou para 'streak', que nunca existiu."""
        self.assertTrue(hasattr(Quarto, 'streak_dias'))
        self.assertFalse(hasattr(Quarto, 'streak'))

    def test_template_nao_usa_mais_o_campo_antigo(self):
        with open(
            str(Path(__file__).resolve().parent / 'templates' / 'painel_estudante.html'),
            encoding='utf-8',
        ) as f:
            html = f.read()
        self.assertNotIn('estudante.quarto.streak|', html)
        self.assertNotIn('{% if streak_atual < 10 %}', html)
        self.assertIn('stringformat:"02d"', html)

    def test_calendario_semanal_intacto(self):
        """O calendario nao pode ter sido tocado."""
        h = self.html()
        for dia in ('Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'):
            self.assertIn(dia, h)


class ModalCentralizadoTests(TestCase):
    """items-center/justify-center so funcionam se o modal virar display:flex ao abrir."""

    def setUp(self):
        self.quarto = Quarto.objects.create(numero='808', bloco='H')
        u_mon = User.objects.create_user('mon_modal', password='x')
        Monitor.objects.create(
            user=u_mon, siape='9988776', cpf='12312312312', bloco_responsavel='H'
        )
        u_est = User.objects.create_user('aluno_modal', password='x')
        Estudante.objects.create(
            user=u_est, matricula='321', cpf='32132132132', quarto=self.quarto
        )

        self.client.force_login(u_mon)
        self.html_monitor = self.client.get(reverse('painel_monitor')).content.decode()

        self.client.force_login(u_est)
        self.html_estudante = self.client.get(reverse('painel_estudante')).content.decode()

    @staticmethod
    def classes(html, element_id):
        m = re.search(r'id="%s"[^>]*?class="([^"]*)"' % element_id, html)
        return m.group(1).split() if m else []

    @staticmethod
    def corpo_js(src, nome):
        """Corpo da funcao JS, do 'function X(' ate a proxima 'function '."""
        for parte in src.split('function ')[1:]:
            if parte.startswith(nome + '('):
                return parte
        return ''

    def checa_base(self, html, modal_id):
        c = self.classes(html, modal_id)
        self.assertTrue(c, 'modal %s nao encontrado' % modal_id)
        for classe in ('fixed', 'inset-0', 'z-50', 'items-center', 'justify-center', 'hidden'):
            self.assertIn(classe, c)
        # 'flex' nao pode estar na base: entra so via JS, junto da remocao de hidden
        self.assertNotIn('flex', c)

    def checa_js(self, html, abrir, fechar):
        corpo_abrir = self.corpo_js(html, abrir)
        corpo_fechar = self.corpo_js(html, fechar)
        self.assertTrue(corpo_abrir, 'funcao %s nao encontrada' % abrir)
        self.assertTrue(corpo_fechar, 'funcao %s nao encontrada' % fechar)
        self.assertIn("classList.remove('hidden')", corpo_abrir)
        self.assertIn("classList.add('flex')", corpo_abrir)
        self.assertIn("classList.add('hidden')", corpo_fechar)
        self.assertIn("classList.remove('flex')", corpo_fechar)

    def test_modal_monitor_estrutura_base(self):
        self.checa_base(self.html_monitor, 'modal-confirmacao')

    def test_modal_estudante_estrutura_base(self):
        self.checa_base(self.html_estudante, 'modal-estudante')

    def test_js_monitor_troca_flex_e_hidden(self):
        self.checa_js(self.html_monitor, 'abrirModal', 'fecharModal')

    def test_js_estudante_troca_flex_e_hidden(self):
        self.checa_js(self.html_estudante, 'abrirModalEstudante', 'fecharModalEstudante')

    def test_modal_fica_fora_do_main(self):
        """O modal precisa ser filho direto do body, fora de containers com overflow."""
        for html, nome in ((self.html_monitor, 'monitor'), (self.html_estudante, 'estudante')):
            self.assertGreater(html.rfind('modal-'), html.rfind('</main>'), nome)

    def test_trava_de_loop_continua_usando_apenas_hidden(self):
        """A trava de loop e separate: nao deve ter ganho 'flex'."""
        self.client.force_login(User.objects.get(username='mon_modal'))
        html = self.client.get(reverse('detalhes_quarto', args=[self.quarto.id])).content.decode()
        botoes = self.classes(html, 'area-botoes')
        self.assertIn('grid', botoes)
        self.assertNotIn('flex', botoes)


