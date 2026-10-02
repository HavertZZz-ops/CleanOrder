from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils import timezone
import calendar

from .models import Estudante, Monitor, Tarefa, Quarto, Vistoria, SolicitacaoReparo

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
@login_required
def painel_monitor(request):
    if hasattr(request.user, 'monitor'):
        
        estudantes = Estudante.objects.all()
        
    
        total_pendentes = Tarefa.objects.filter(status='Pendente').count()

        contexto = {
            'estudantes': estudantes,
            'total_pendentes': total_pendentes,
            'total_quartos': estudantes.count(),
          
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
          
            nota_raw = request.POST.get('nota')
            nota = nota_raw if nota_raw else None
            
            observacoes = request.POST.get('observacoes')
            aprovado = request.POST.get('aprovado') == 'True'

            
            Vistoria.objects.create(
                monitor=request.user.monitor,
                quarto=quarto_selecionado,
                nota=nota,
                observacoes=observacoes,
                aprovado=aprovado
            )
            
           
            if quarto_selecionado.streak_dias is None:
                quarto_selecionado.streak_dias = 0
                
            
            if aprovado:
                quarto_selecionado.status = 'Aprovado'
                quarto_selecionado.streak_dias += 1
            else:
                quarto_selecionado.status = 'Pendente' 
                quarto_selecionado.streak_dias = 0
                
           
            quarto_selecionado.save()

            messages.success(request, 'Vistoria guardada com sucesso!')
            return redirect('painel_monitor')

       
        estudantes = Estudante.objects.all()
        total_pendentes = Tarefa.objects.filter(status='Pendente').count()

        contexto = {
            'estudantes': estudantes,
            'total_pendentes': total_pendentes,
            'total_quartos': estudantes.count(),
            'quarto_selecionado': quarto_selecionado 
        }

        return render(request, 'painel_monitor.html', contexto)

    elif hasattr(request.user, 'estudante'):
        return redirect('painel_estudante')
    else:
        logout(request)
        return redirect('login')
@login_required
def reportar_problema(request):
    
    if hasattr(request.user, 'estudante'):
        
        
        if request.method == 'POST':
            titulo = request.POST.get('titulo')
            categoria = request.POST.get('categoria')
            descricao = request.POST.get('descricao')
            
            
            messages.success(request, 'Problema reportado com sucesso! A manutenção foi notificada.')
            return redirect('painel_estudante')
            
       
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
        
        
        
        vistorias_mes = Vistoria.objects.filter(
            quarto=quarto,
            aprovado=True,
            data_vistoria__year=hoje.year,
            data_vistoria__month=hoje.month
        )
        dias_aprovados = list(vistorias_mes.values_list('data_vistoria__day', flat=True))
        
        contexto = {
            'estudante': estudante,
            'tarefas': tarefas,
            'total_tarefas': total_tarefas,
            'tarefas_concluidas': tarefas_concluidas,
            'progresso_percentual': progresso_percentual,
            'hoje': hoje,
            'todos_os_dias': todos_os_dias,
            'dias_aprovados': dias_aprovados,
            'streak_atual': quarto.streak_dias
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
        quarto = estudante.quarto
        
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