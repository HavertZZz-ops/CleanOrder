from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import calendar

from .models import Estudante, Monitor, Tarefa, Quarto, Vistoria, SolicitacaoReparo

# Pesos de cada critério da vistoria. Somam 10 (escala de 0 a 10).
# Nomes e pesos espelham exatamente os checkboxes do painel do monitor.
# Origem: entrevista de validação com o monitor do alojamento.
CRITERIOS_VISTORIA = {
    'chao_lavanderia': 4,
    'organizacao_geral': 3,
    'janelas_livres': 3,
}


def login_view(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'estudante'):
            return redirect('painel_estudante')
        elif hasattr(request.user, 'monitor'):
            return redirect('painel_monitor')
        else:
            return redirect('/admin/')

    if request.method == 'POST':
        cpf_digitado = request.POST.get('cpf')
        senha_digitada = request.POST.get('password')
        username_para_login = cpf_digitado

        try:
            estudante_encontrado = Estudante.objects.get(cpf=cpf_digitado)
            username_para_login = estudante_encontrado.user.username
        except Estudante.DoesNotExist:
            try:
                monitor_encontrado = Monitor.objects.get(cpf=cpf_digitado)
                username_para_login = monitor_encontrado.user.username
            except Monitor.DoesNotExist:
                pass
                
        usuario = authenticate(request, username=username_para_login, password=senha_digitada)

        if usuario is not None:
            login(request, usuario)
            if hasattr(usuario, 'estudante'):
                return redirect('painel_estudante')
            elif hasattr(usuario, 'monitor'):
                return redirect('painel_monitor')
            else:
                return redirect('/admin/')
        else:
            messages.error(request, 'CPF ou senha inválidos. Tente novamente.')
            return redirect('login')

    return render(request, 'login.html')

def fazer_logout(request):
    logout(request)
    messages.success(request, 'Logout realizado com sucesso.')
    return redirect('login')

@login_required
def painel_estudante(request):
    if hasattr(request.user, 'estudante'):
        estudante = request.user.estudante
        tarefas = Tarefa.objects.filter(estudante_responsavel=estudante)
        contexto = {
            'estudante': estudante,
            'tarefas': tarefas
        }
        return render(request, 'painel_estudante.html', contexto)
    elif hasattr(request.user, 'monitor'):
        return redirect('painel_monitor')
    else:
        logout(request)
        messages.error(request, 'Acesso negado: Sua conta não possui um perfil válido. Procure a administração.')
        return redirect('login')
@login_required
def concluir_tarefa(request, tarefa_id):
    if not hasattr(request.user, 'estudante'):
        messages.error(request, 'Apenas estudantes podem concluir tarefas.')
        return redirect('login')

   
    tarefa = get_object_or_404(Tarefa, id=tarefa_id, estudante_responsavel=request.user.estudante)

   
    if tarefa.status == 'Concluída':
        tarefa.status = 'Pendente'
    else:
        tarefa.status = 'Concluída'
    
    tarefa.save()

    messages.success(request, 'Status da tarefa atualizado com sucesso!')
    return redirect('painel_estudante')
def chamados_do_monitor():
    """Chamados de infraestrutura abertos, do mais recente para o mais antigo."""
    return SolicitacaoReparo.objects.select_related('estudante').order_by('-data_abertura')[:20]


@login_required
def painel_monitor(request):
    if hasattr(request.user, 'monitor'):

        estudantes = Estudante.objects.select_related('quarto').all()

        total_pendentes = Tarefa.objects.filter(status='Pendente').count()

        contexto = {
            'estudantes': estudantes,
            'total_pendentes': total_pendentes,
            'total_quartos': estudantes.count(),
            'reparos': chamados_do_monitor(),
        }
        return render(request, 'painel_monitor.html', contexto)

        
    elif hasattr(request.user, 'estudante'):
        return redirect('painel_estudante')
    else:
        logout(request)
        messages.error(request, 'Acesso negado.')
        return redirect('login')
@login_required
def detalhes_quarto(request, quarto_id):
    if hasattr(request.user, 'monitor'):
        quarto_selecionado = get_object_or_404(Quarto, id=quarto_id)

        if request.method == 'POST':
            # Nota calculada a partir dos critérios marcados (0 a 10).
            nota = sum(
                peso
                for criterio, peso in CRITERIOS_VISTORIA.items()
                if request.POST.get(criterio) == '1'
            )

            observacoes = request.POST.get('observacoes', '')
            aprovado = request.POST.get('aprovado') == 'True'

            Vistoria.objects.create(
                monitor=request.user.monitor,
                quarto=quarto_selecionado,
                nota=nota,
                observacoes=observacoes,
                aprovado=aprovado
            )

            if aprovado:
                quarto_selecionado.status = Quarto.STATUS_APROVADO
                quarto_selecionado.streak_dias = (quarto_selecionado.streak_dias or 0) + 1
            else:
                quarto_selecionado.status = Quarto.STATUS_REPROVADO
                quarto_selecionado.streak_dias = 0

            quarto_selecionado.save()

            messages.success(request, 'Vistoria guardada com sucesso!')
            return redirect('detalhes_quarto', quarto_id=quarto_selecionado.id)

        estudantes = Estudante.objects.select_related('quarto').all()
        total_pendentes = Tarefa.objects.filter(status='Pendente').count()

        contexto = {
            'estudantes': estudantes,
            'total_pendentes': total_pendentes,
            'total_quartos': estudantes.count(),
            'quarto_selecionado': quarto_selecionado,
            'ultima_vistoria': (
                Vistoria.objects.filter(quarto=quarto_selecionado)
                .order_by('-data_vistoria', '-id')
                .first()
            ),
            'reparos': chamados_do_monitor(),
        }

        return render(request, 'painel_monitor.html', contexto)

    elif hasattr(request.user, 'estudante'):
        return redirect('painel_estudante')
    else:
        logout(request)
        return redirect('login')

@login_required
def verificar_reparo(request, reparo_id):
    """Monitor confirma que visitou o dano e marcou o chamado como Verificado."""
    if request.method != 'POST':
        return redirect('painel_monitor')

    if not hasattr(request.user, 'monitor'):
        messages.warning(request, 'Apenas monitores podem verificar chamados.')
        return redirect('painel_monitor')

    reparo = get_object_or_404(SolicitacaoReparo, id=reparo_id)
    reparo.status = 'Verificado'
    reparo.save(update_fields=['status'])

    messages.success(request, f'Chamado #{reparo.id} marcado como verificado.')
    return redirect('painel_monitor')

@login_required
def reportar_problema(request):

    if hasattr(request.user, 'estudante'):
        # O formulário em reportar_problema.html posta para 'enviar_relatorio'.
        # Se um POST chegar aqui, delegamos para lá em vez de fingir sucesso.
        if request.method == 'POST':
            return enviar_relatorio(request)

        return render(request, 'reportar_problema.html')

    elif hasattr(request.user, 'monitor'):
        messages.warning(request, 'Monitores não podem reportar problemas por esta tela.')
        return redirect('painel_monitor')

    else:
        return redirect('login')


@login_required
def progresso(request):
    if hasattr(request.user, 'estudante'):
        estudante = request.user.estudante
        quarto = estudante.quarto

        tarefas = Tarefa.objects.filter(estudante_responsavel=estudante)
        total_tarefas = tarefas.count()
        tarefas_concluidas = tarefas.filter(status='Concluída').count()
        progresso_percentual = (tarefas_concluidas / total_tarefas * 100) if total_tarefas > 0 else 0

        hoje = timezone.now()
        _, num_dias = calendar.monthrange(hoje.year, hoje.month)
        todos_os_dias = list(range(1, num_dias + 1))

        dias_aprovados = []
        streak_atual = 0
        if quarto is not None:
            vistorias_mes = Vistoria.objects.filter(
                quarto=quarto,
                aprovado=True,
                data_vistoria__year=hoje.year,
                data_vistoria__month=hoje.month
            )
            dias_aprovados = list(vistorias_mes.values_list('data_vistoria__day', flat=True))
            streak_atual = quarto.streak_dias or 0
        else:
            messages.warning(request, 'Você ainda não tem um quarto vinculado. O progresso do quarto ficará indisponível.')

        contexto = {
            'estudante': estudante,
            'quarto': quarto,
            'sem_quarto': quarto is None,
            'tarefas': tarefas,
            'total_tarefas': total_tarefas,
            'tarefas_concluidas': tarefas_concluidas,
            'progresso_percentual': progresso_percentual,
            'hoje': hoje,
            'todos_os_dias': todos_os_dias,
            'dias_aprovados': dias_aprovados,
            'streak_atual': streak_atual
        }

        return render(request, 'progresso.html', contexto)

    elif hasattr(request.user, 'monitor'):
        return redirect('painel_monitor')

    else:
        logout(request)
        messages.error(request, 'Acesso negado.')
        return redirect('login')

@login_required
def enviar_relatorio(request):
    if hasattr(request.user, 'estudante'):
        estudante = request.user.estudante

        if request.method == 'POST':
            titulo = request.POST.get('titulo')
            categoria = request.POST.get('categoria')
            descricao = request.POST.get('descricao')

            SolicitacaoReparo.objects.create(
                estudante=estudante,
                titulo=titulo,
                categoria=categoria,
                descricao=descricao,
                status='Em Aberto'
            )

            messages.success(request, 'Problema reportado com sucesso! A manutenção foi notificada.')
            return redirect('painel_estudante')

        return render(request, 'reportar_problema.html')

    elif hasattr(request.user, 'monitor'):
        messages.warning(request, 'Monitores não podem reportar problemas por esta tela.')
        return redirect('painel_monitor')

    else:
        return redirect('login')