from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
import firebase_admin
from firebase_admin import firestore
from firebase_admin import credentials
from django.conf import settings
from django.views.decorators.http import require_POST
from google.api_core.datetime_helpers import DatetimeWithNanoseconds
import time
import io
import random
import pytz
from datetime import datetime, timedelta
from unidecode import unidecode
from functools import wraps
import plotly.graph_objects as go
import pandas as pd
import plotly.express as px
import json
from collections import defaultdict
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa

def login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        print("Verificando sessão:", request.session.get('user'))
        if 'user' not in request.session:
            print("Sem sessão, redirecionando ao login")
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper

def login_submit(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        cpf = request.POST.get('access_key')

        db = initialize_firebase()
        funcionarios_ref = db.collection('funcionarios')
        query = funcionarios_ref.where('nome_funcionario', '==', username).where('cpf_funcionario', '==', cpf)
        resultados = list(query.stream())

        if resultados:
            funcionario_data = resultados[0].to_dict()
            nome = funcionario_data.get('nome_funcionario')
            cpf = funcionario_data.get('cpf_funcionario')
            cargo = funcionario_data.get('cargo_funcionario')

            request.session['user'] = {
                'nome': nome,
                'cpf': cpf,
                'cargo': cargo
            }

            print("Sessão criada:", request.session.get('user'))
            return redirect('dashboard')
        else:
            return render(request, 'login/login.html', {'error_message': 'Credenciais inválidas.'})
    else:
        return redirect('login')

    
def logout_view(request):
    request.session.flush() 
    return redirect('login')

# Isso aqui é o que tá inicializando o firebase, NAO MEXE

def initialize_firebase():
    if not firebase_admin._apps:
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# Caminhos das páginas

def login_view(request):
    return render(request, 'login/login.html')

@login_required
def dashboard_view(request):
    user = request.session.get('user')
    db = initialize_firebase()
    produtos_ref = db.collection('produtos').stream()

    faixas = {
        '0-3 dias': 0,
        '4-7 dias': 0,
        '8-15 dias': 0,
        '16-30 dias': 0,
        '+30 dias': 0,
    }
    hoje = datetime.now().date()

    produtos_data = []
    total_estoque = 0
    produtos_proximos_validade = 0
    produtos_vencidos = 0

    for produto in produtos_ref:
        data = produto.to_dict()

        qtd_total = int(data.get('qtd_total', 0))
        total_estoque += qtd_total

        data_validade_raw = data.get('data_validade')
        data_validade = None
        if data_validade_raw:
            if isinstance(data_validade_raw, str):
                try:
                    data_validade = datetime.strptime(data_validade_raw, "%Y-%m-%d").date()
                except:
                    data_validade = None
            else:
                data_validade = data_validade_raw.replace(tzinfo=None).date()

        if data_validade:
            dias_restantes = (data_validade - hoje).days

            if dias_restantes < 0:
                produtos_vencidos += qtd_total
            elif dias_restantes <= 30:
                produtos_proximos_validade += qtd_total

            if dias_restantes >= 0:
                if dias_restantes <= 3:
                    faixas['0-3 dias'] += 1
                elif dias_restantes <= 7:
                    faixas['4-7 dias'] += 1
                elif dias_restantes <= 15:
                    faixas['8-15 dias'] += 1
                elif dias_restantes <= 30:
                    faixas['16-30 dias'] += 1
                else:
                    faixas['+30 dias'] += 1

        categoria = data.get('categoria', 'Sem Categoria')

        produtos_data.append({
            'categoria': categoria,
            'quantidade': qtd_total
        })

    # Gráfico de validade (barras)
    fig_validade = go.Figure(data=[go.Bar(
        x=list(faixas.keys()),
        y=list(faixas.values()),
        marker_color=['crimson', 'orange', 'yellow', 'lightgreen', 'green']
    )])
    fig_validade.update_layout(
        title=dict(text='Lotes Próximos da Validade', font=dict(size=18), x=0.5),
        xaxis_title='Faixa de Dias Restantes',
        yaxis_title='Quantidade de Lotes',
        template='plotly_white',
        width=450,
        height=300,
        margin=dict(l=40, r=40, t=60, b=40),
        font=dict(size=10)
    )

    # Gráfico de pizza: estoque por categoria
    df = pd.DataFrame(produtos_data)
    if not df.empty:
        df_agrupado = df.groupby('categoria', as_index=False)['quantidade'].sum()
    else:
        df_agrupado = pd.DataFrame(columns=['categoria', 'quantidade'])

    fig_estoque = px.pie(
    df_agrupado,
    names='categoria',
    values='quantidade',
    hole=0.3,  # gráfico com "buraco" no meio
)

    fig_estoque.update_traces(
    textposition='inside',
    textinfo='percent+label'
)

    fig_estoque.update_layout(
    title=dict(
        text='Distribuição de Estoque por Categoria',
        font=dict(size=14),
        x=0.5,
        xanchor='center'
    ),
    legend=dict(
        orientation="h",
        x=0.5,
        y=-0.15, 
        xanchor='center',
        yanchor='top',
        font=dict(size=12)
    ),
    width=300,
    height=635,
    margin=dict(t=50, l=25, r=25, b=60),
    font=dict(size=12),
)

    # ➤ NOVO: Faturamento por Categoria (barras)
    vendas_ref = db.collection('vendas').stream()
    faturamento_categoria = defaultdict(float)
    faturamento_diario = defaultdict(float)

    for venda in vendas_ref:
        data = venda.to_dict()
        itens = data.get('itens', [])
        total = data.get('total', 0)
        data_venda = data.get('data')

        # Faturamento diário (para gráfico de linha)
        if data_venda:
            if isinstance(data_venda, str):
                data_venda = datetime.strptime(data_venda, "%Y-%m-%dT%H:%M:%S%z")
            else:
                data_venda = data_venda.astimezone(pytz.timezone('America/Sao_Paulo'))
            dia = data_venda.date().strftime('%d/%m')
            faturamento_diario[dia] += total

        # Faturamento por categoria
        for item in itens:
            cod = item.get('codigo')
            qtd = item.get('qtd', 0)
            preco = item.get('preco', 0)

            # Recupera categoria do produto
            prod_ref = db.collection('produtos').where('cod_produto', '==', cod).limit(1).stream()
            prod_doc = next(prod_ref, None)

            if prod_doc:
                categoria = prod_doc.to_dict().get('categoria', 'Sem Categoria')
                faturamento_categoria[categoria] += qtd * preco

    # ➤ Gráfico de barras - Faturamento por Categoria
    categorias = list(faturamento_categoria.keys())
    totais_cat = list(faturamento_categoria.values())

    fig_categoria = go.Figure(data=[go.Bar(
        x=categorias,
        y=totais_cat,
        marker_color='lightskyblue',
        name='Faturamento por Categoria'
    )])
    fig_categoria.update_layout(
        title='Faturamento por Categoria',
        xaxis_title='Categoria',
        yaxis_title='Faturamento (R$)',
        template='plotly_white',
        width=450,
        height=300,
        font=dict(size=12)
    )

    # ➤ Gráfico de linha - Faturamento Diário
    faturamento_ordenado = sorted(faturamento_diario.items(), key=lambda x: datetime.strptime(x[0], "%d/%m"))
    dias = [x[0] for x in faturamento_ordenado]
    totais = [x[1] for x in faturamento_ordenado]

    fig_faturamento = go.Figure()
    fig_faturamento.add_trace(go.Scatter(
        x=dias,
        y=totais,
        mode='lines+markers',
        name='Faturamento Diário',
        line=dict(shape='spline', color='mediumseagreen', width=3),
        marker=dict(size=6)
    ))
    fig_faturamento.update_layout(
        title='Faturamento Diário',
        xaxis_title='Data',
        yaxis_title='Total (R$)',
        template='plotly_white',
        width=940,
        height=300,
        margin=dict(l=40, r=40, t=60, b=40),
        font=dict(size=12)
    )

    return render(request, 'dashboard/dashboard.html', {
        'grafico_validade_div': fig_validade.to_html(full_html=False),
        'grafico_estoque_div': fig_estoque.to_html(full_html=False),
        'grafico_faturamento_categoria': fig_categoria.to_html(full_html=False),
        'grafico_faturamento_diario': fig_faturamento.to_html(full_html=False),
        'user': user,
        'total_produtos': total_estoque,
        'produtos_proximos_validade': produtos_proximos_validade,
        'produtos_vencidos': produtos_vencidos,
    })

@login_required
def produtos_view(request):
    user = request.session.get('user')
    return render(request, 'produtos/produtos.html', {'user': user})

@login_required
def funcionarios_view(request):
    user = request.session.get('user')
    return render(request, 'funcionarios/funcionarios.html', {'user': user})

@login_required
def estatisticas_view(request):
    user = request.session.get('user')
    return render(request, 'estatisticas/estatisticas.html', {'user': user})

@login_required
def historico_view(request):
    history = request.session.get('history', [])
    nomes_paginas = {
        '/dashboard/': 'Dashboard',
        '/produtos/': 'Produtos',
        '/funcionarios/': 'Funcionários',
        '/estatisticas/': 'Estatísticas',
        '/relatorios/': 'Relatórios',
        '/estabelecer_acao/': 'Estabelecer Ação',
        '/historico/': 'Histórico de Consulta',
        '/politica/': 'Política e Segurança',
    }
    return render(request, 'historico/historico.html', {
        'history': history,
        'nomes_paginas': nomes_paginas,
        'user': request.session.get('user'),
    })

@login_required
def politica_view(request):
    user = request.session.get('user')
    return render(request, 'politica/politica.html', {'user': user})

def relatorios_view(request):
    user = request.session.get('user')
    tipo_relatorio = request.GET.get('tipo_relatorio', '').strip()
    
    def to_int_or_default(value, default=30):
        try:
            ivalue = int(value)
            return ivalue if ivalue > 0 else default
        except (ValueError, TypeError):
            return default

    db = initialize_firebase()
    contexto = {'user': user, 'tipo_relatorio': tipo_relatorio}

    if tipo_relatorio == 'produtos_proximos_validade':
        dias = to_int_or_default(request.GET.get('dias'), 30)
        hoje = datetime.now(pytz.UTC)
        limite = hoje + timedelta(days=dias)

        produtos_ref = db.collection('produtos')
        produtos = produtos_ref.stream()

        resultado = []
        for produto in produtos:
            data = produto.to_dict()
            data_validade = data.get('data_validade')
            if not data_validade:
                continue

            if isinstance(data_validade, str):
                try:
                    data_validade_dt = datetime.strptime(data_validade, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
                except:
                    continue
            else:
                data_validade_dt = data_validade

            if hoje <= data_validade_dt <= limite:
                resultado.append({
                    'nome_produto': data.get('nome_produto'),
                    'cod_produto': data.get('cod_produto'),
                    'qtd_total': data.get('qtd_total'),
                    'categoria': data.get('categoria'),
                    'data_validade': data_validade_dt.date(),
                    'preco_produto': data.get('preco_produto'),
                })

        resultado.sort(key=lambda x: x['data_validade'])

        contexto.update({
            'produtos': resultado,
            'dias': dias,
        })

    elif tipo_relatorio == 'produtos_vencidos':
        data_inicio_str = request.GET.get('data_inicio', None)
        data_fim_str = request.GET.get('data_fim', None)
        categoria_filtro = request.GET.get('categoria', '').strip().lower()

        hoje = datetime.now(pytz.UTC).date()

        # Parse datas ou usar defaults
        try:
            data_inicio = datetime.strptime(data_inicio_str, '%Y-%m-%d').date() if data_inicio_str else datetime(2000, 1, 1).date()
        except Exception:
            data_inicio = datetime(2000, 1, 1).date()
        try:
            data_fim = datetime.strptime(data_fim_str, '%Y-%m-%d').date() if data_fim_str else hoje
        except Exception:
            data_fim = hoje

        produtos_ref = db.collection('produtos')
        produtos = produtos_ref.stream()

        resultado = []
        for produto in produtos:
            data = produto.to_dict()
            data_validade = data.get('data_validade')
            if not data_validade:
                continue

            if isinstance(data_validade, str):
                try:
                    data_validade_dt = datetime.strptime(data_validade, "%Y-%m-%d").date()
                except:
                    continue
            else:
                if hasattr(data_validade, 'date'):
                    data_validade_dt = data_validade.date()
                else:
                    data_validade_dt = data_validade

            if data_inicio <= data_validade_dt <= data_fim and data_validade_dt < hoje:
                if categoria_filtro and categoria_filtro != data.get('categoria', '').lower():
                    continue

                resultado.append({
                    'nome_produto': data.get('nome_produto'),
                    'cod_produto': data.get('cod_produto'),
                    'qtd_total': data.get('qtd_total'),
                    'categoria': data.get('categoria'),
                    'data_validade': data_validade_dt,
                    'preco_produto': data.get('preco_produto'),
                })

        resultado.sort(key=lambda x: x['data_validade'], reverse=True)

        contexto.update({
            'produtos': resultado,
            'data_inicio': data_inicio_str,
            'data_fim': data_fim_str,
            'categoria': categoria_filtro,
        })

    elif tipo_relatorio == 'estoque_categoria':
        categoria_filtro = request.GET.get('categoria', '').strip().lower()

        produtos_ref = db.collection('produtos')
        produtos = produtos_ref.stream()

        categorias = {}

        for produto in produtos:
            data = produto.to_dict()
            categoria = data.get('categoria', 'Sem Categoria')

            if categoria_filtro and categoria_filtro != categoria.lower():
                continue

            qtd = data.get('qtd_total', 0)
            preco = data.get('preco_produto', 0)

            if categoria not in categorias:
                categorias[categoria] = {'quantidade': 0, 'valor': 0}

            categorias[categoria]['quantidade'] += qtd
            categorias[categoria]['valor'] += qtd * preco

        resultado = [{'categoria': k, 'quantidade': v['quantidade'], 'valor': v['valor']} for k, v in categorias.items()]
        contexto.update({
            'categorias': resultado,
            'categoria_filtro': categoria_filtro,
        })

    return render(request, 'relatorios/relatorios.html', contexto)

@login_required
def relatorio_pdf(request):
    db = initialize_firebase()
    tipo_relatorio = request.GET.get('tipo_relatorio')
    context = {}

    if tipo_relatorio == 'produtos_proximos_validade':
        dias = int(request.GET.get('dias', 30))
        hoje = datetime.now(pytz.UTC)
        limite = hoje + timedelta(days=dias)

        produtos_ref = db.collection('produtos')
        produtos = []
        for produto in produtos_ref.stream():
            p = produto.to_dict()
            data_val = p.get('data_validade')
            if not data_val:
                continue
            if isinstance(data_val, datetime):
                data_val = data_val.replace(tzinfo=None)
            if hoje.replace(tzinfo=None) <= data_val <= limite.replace(tzinfo=None):
                produtos.append(p)

        context = {
            'produtos': produtos,
            'titulo': f"Produtos Próximos da Validade (até {dias} dias)",
        }

    elif tipo_relatorio == 'produtos_vencidos':
        data_inicio = request.GET.get('data_inicio')
        data_fim = request.GET.get('data_fim')
        categoria_filtro = request.GET.get('categoria', '').strip()

        try:
            dt_inicio = datetime.strptime(data_inicio, '%Y-%m-%d') if data_inicio else datetime(2000,1,1)
            dt_fim = datetime.strptime(data_fim, '%Y-%m-%d') if data_fim else datetime.now()
        except Exception:
            dt_inicio = datetime(2000,1,1)
            dt_fim = datetime.now()

        produtos_ref = db.collection('produtos')
        produtos = []
        for produto in produtos_ref.stream():
            p = produto.to_dict()
            data_val = p.get('data_validade')
            if not data_val:
                continue
            if isinstance(data_val, datetime):
                data_val = data_val.replace(tzinfo=None)
            if dt_inicio <= data_val <= dt_fim:
                if categoria_filtro:
                    if p.get('categoria','').lower() == categoria_filtro.lower():
                        produtos.append(p)
                else:
                    produtos.append(p)

        filtro_texto = f" - Categoria: {categoria_filtro}" if categoria_filtro else ""
        context = {
            'produtos': produtos,
            'titulo': f"Produtos Vencidos{filtro_texto}",
            'data_inicio': dt_inicio.date(),
            'data_fim': dt_fim.date(),
            'categoria': categoria_filtro,
        }

    elif tipo_relatorio == 'estoque_categoria':
        categoria_filtro = request.GET.get('categoria', '').strip()

        produtos_ref = db.collection('produtos')
        categorias_dict = {}

        for produto in produtos_ref.stream():
            p = produto.to_dict()
            categoria = p.get('categoria', 'Sem Categoria')
            if categoria_filtro and categoria.lower() != categoria_filtro.lower():
                continue

            qtd = p.get('qtd_total', 0) or 0
            preco = p.get('preco_produto', 0) or 0
            if categoria not in categorias_dict:
                categorias_dict[categoria] = {'quantidade': 0, 'valor': 0.0}
            categorias_dict[categoria]['quantidade'] += qtd
            categorias_dict[categoria]['valor'] += qtd * preco

        categorias = []
        for cat, dados in categorias_dict.items():
            categorias.append({
                'categoria': cat,
                'quantidade': dados['quantidade'],
                'valor': dados['valor'],
            })

        context = {
            'categorias': categorias,
            'titulo': "Estoque por Categoria" + (f" - {categoria_filtro}" if categoria_filtro else ""),
            'categoria_filtro': categoria_filtro,
        }

    else:
        return HttpResponse("Tipo de relatório inválido", status=400)
    
    user = request.session.get('user', {})
    context['usuario'] = user.get('nome', 'Usuário Desconhecido')
    context['agora'] = datetime.now()
    # Renderiza o template para HTML
    html_string = render_to_string('relatorios/relatorio_pdf_template.html', context)

    # Gera PDF usando xhtml2pdf
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename=relatorio_{tipo_relatorio}.pdf'

    pisa_status = pisa.CreatePDF(io.BytesIO(html_string.encode('UTF-8')), dest=response)
    if pisa_status.err:
        return HttpResponse('Erro ao gerar PDF', status=500)
    return response

# CRUD Produtos
@login_required
def addProdutos(request):
    if request.method == 'POST':
        db = initialize_firebase()

        cod_produto = request.POST.get('codProduto')
        nome_produto = request.POST.get('nomeProduto')
        preco_produto = float(request.POST.get('precoProduto', 0))
        qtd_produto = int(request.POST.get('qntCxProduto', 0))
        qtd_produtoPCx = int(request.POST.get('qntPCxProduto', 0))
        lote_produto = request.POST.get('loteProduto')
        data_fab_str = request.POST.get('dataFabProduto')
        data_val_str = request.POST.get('dataValProduto')
        categoria_produto = request.POST.get('categoriaProduto')

        try:
            data_fab = datetime.strptime(data_fab_str, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
            data_val = datetime.strptime(data_val_str, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
            qtd_total = qtd_produto * qtd_produtoPCx

            doc_ref = db.collection("produtos").document()
            doc_ref.set({
                "cod_produto": cod_produto,
                "nome_produto": nome_produto,
                "preco_produto": preco_produto,
                "qtd_produto": qtd_produto,
                "lote_produto": lote_produto,
                "data_fabricacao": data_fab,
                "data_validade": data_val,
                "qtd_produtoPCx": qtd_produtoPCx,
                "qtd_total": qtd_total,
                "categoria": categoria_produto
            })

            time.sleep(5)

            return render(request, 'produtos/produtos.html')  

        except Exception as e:
            return render(request, 'produtos/produtos.html', {'erro': str(e)})

    return redirect('produtos')

@login_required
def listProdutos_view(request):
    db = initialize_firebase()

    termo = request.GET.get('searchProduto', '').strip().lower()
    termo_sem_acentos = unidecode(termo)

    produtos_ref = db.collection('produtos')
    produtos = produtos_ref.stream()

    categorias_ref = db.collection('categorias')
    categorias = categorias_ref.stream()

    produtos_list = []
    for produto in produtos:
        data = produto.to_dict()
        data['id'] = produto.id

        nome = unidecode(data.get('nome_produto', '').lower())
        categoria = unidecode(data.get('categoria', '').lower())
        codigo = unidecode(data.get('cod_produto', '').lower())

        if termo_sem_acentos in nome or termo_sem_acentos in categoria or termo_sem_acentos in codigo or termo == '':
            produtos_list.append(data)

    categorias_list = []
    for categoria in categorias:
        cat_data = categoria.to_dict()
        cat_data['id'] = categoria.id
        categorias_list.append(cat_data)

    context = {
        'produtos': produtos_list,
        'categorias': categorias_list,
        'user': request.session.get('user'),
    }

    return render(request, 'produtos/produtos.html', context)

@login_required
def editar_produto(request, id):
    if request.method == 'POST':
        db = initialize_firebase()

        try:
            data_fab_str = request.POST.get('dataFabProduto')
            data_val_str = request.POST.get('dataValProduto')

            data_fab = datetime.strptime(data_fab_str, "%Y-%m-%d").replace(tzinfo=pytz.UTC)
            data_val = datetime.strptime(data_val_str, "%Y-%m-%d").replace(tzinfo=pytz.UTC)

            produto_ref = db.collection('produtos').document(id)
            produto_ref.update({
                'cod_produto': request.POST.get('codProduto'),
                'nome_produto': request.POST.get('nomeProduto'),
                'categoria': request.POST.get('categoriaProduto'),
                'preco_produto': float(request.POST.get('precoProduto')),
                'qtd_produtoPCx': int(request.POST.get('qntCxProduto', 0)),
                'qtd_produto': int(request.POST.get('qntPCxProduto', 0)),
                'lote_produto': request.POST.get('loteProduto'),
                'data_fabricacao': data_fab,
                'data_validade': data_val,
            })

            return redirect('produtos')

        except ValueError:
            return JsonResponse({"success": False, "error": "Formato de data inválido. Use AAAA-MM-DD."})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)

@login_required    
@require_POST
def delete_produto(request):
    db = initialize_firebase()
    print("DELETE ACIONADO")
    produto_id = request.POST.get('id')
    print("ID recebido:", produto_id)
    if produto_id:
        db.collection('produtos').document(produto_id).delete()
        print("Documento deletado")
    else:
        print("Nenhum ID recebido")
    return redirect('produtos')


# CRUD Ações

@login_required
def addAcao(request):
    if request.method == 'POST':
        db = initialize_firebase()

        nome_acao = request.POST.get('nomeAcao')
        desc_acao = request.POST.get('descAcao')
        resp_acao = request.POST.get('respAcao')
        urge_acao = request.POST.get('urgeAcao')

        doc_ref = db.collection("tarefas").document()
        doc_ref.set({
            "nome_acao": nome_acao,
            "desc_acao": desc_acao,
            "resp_acao": resp_acao,
            "urge_acao": urge_acao,
        })

        print("Tarefa cadastrada com sucesso") 

        time.sleep(5)

        return redirect('estabelecer_acao')
    else:
        return JsonResponse({"erro": "Método não permitido"}, status=405)

@login_required    
def listAcao_view(request):
    db = initialize_firebase()

    # --- Busca funcionários para montar dicionário de nomes e lista de repositores ---
    funcionarios_ref = db.collection('funcionarios')
    funcionarios = funcionarios_ref.stream()
    funcionarios_dict = {}
    funcionarios_list = []
    repositores = []  # lista nomes de repositores para atribuir tarefas

    for funcionario in funcionarios:
        func_data = funcionario.to_dict()
        func_data['id'] = funcionario.id
        funcionarios_list.append(func_data)
        funcionarios_dict[funcionario.id] = func_data.get('nome_funcionario', 'Desconhecido')

        # Se cargo for "repositor", adiciona na lista
        cargo = func_data.get('cargo_funcionario', '').lower()
        nome_func = func_data.get('nome_funcionario', '')
        if cargo == 'repositor':
            repositores.append(nome_func)

    # --- Verificar produtos perto de vencer e criar tarefas automáticas ---
    produtos_ref = db.collection('produtos')
    produtos = produtos_ref.stream()

    hoje = datetime.now().date()
    limite = hoje + timedelta(days=30)  # alerta para produtos vencendo em até 30 dias

    tarefas_ref = db.collection('tarefas')
    tarefas = list(tarefas_ref.stream())

    tarefas_existentes_descricoes = set()
    for tarefa in tarefas:
        tdata = tarefa.to_dict()
        descr = tdata.get('desc_acao', '')
        tarefas_existentes_descricoes.add(descr)

    for produto in produtos:
        produto_data = produto.to_dict()
        data_validade_raw = produto_data.get('data_validade')

        if not data_validade_raw:
            continue

        # Converter para datetime.date corretamente
        if isinstance(data_validade_raw, str):
            try:
                data_validade = datetime.strptime(data_validade_raw, "%Y-%m-%d").date()
            except Exception as e:
                print(f"Erro ao converter string data_validade do produto {produto_data.get('nome_produto')}: {e}")
                continue
        elif isinstance(data_validade_raw, DatetimeWithNanoseconds):
            data_validade = data_validade_raw.replace(tzinfo=None).date()
        else:
            print(f"Tipo desconhecido para data_validade do produto {produto_data.get('nome_produto')}: {type(data_validade_raw)}")
            continue

        if hoje <= data_validade <= limite:
            descricao_tarefa = f"Produto '{produto_data.get('nome_produto')}' do lote {produto_data.get('lote_produto')} vence em {data_validade.strftime('%Y-%m-%d')}"

            # Evita duplicar tarefas iguais
            if descricao_tarefa not in tarefas_existentes_descricoes:
                responsavel_aleatorio = random.choice(repositores) if repositores else ""

                doc_ref = tarefas_ref.document()
                doc_ref.set({
                    "nome_acao": f"Produto '{produto_data.get('nome_produto')}' perto do vencimento",
                    "desc_acao": descricao_tarefa,
                    "resp_acao": responsavel_aleatorio,
                    "urge_acao": "Alta",
                })
                print(f"Tarefa criada para produto {produto_data.get('nome_produto')} vencendo em {data_validade.strftime('%Y-%m-%d')} atribuída a {responsavel_aleatorio}")
            else:
                print(f"Tarefa para produto {produto_data.get('nome_produto')} já existe, ignorando.")

    # --- Filtrar e montar lista de tarefas para renderizar ---
    termo = request.GET.get('searchAcao', '').strip().lower()
    termo_sem_acentos = unidecode(termo)

    tarefas_ref = db.collection('tarefas')
    tarefas = tarefas_ref.stream()

    tarefas_list = []
    for tarefa in tarefas:
        tarefa_data = tarefa.to_dict()
        tarefa_data['id'] = tarefa.id

        resp_id = tarefa_data.get('resp_acao')
        nome_responsavel = resp_id if resp_id else 'Desconhecido'  # Como agora é nome, usamos direto
        tarefa_data['nome_responsavel'] = nome_responsavel

        titulo = unidecode(tarefa_data.get('nome_acao', '').lower())
        nome_resp = unidecode(nome_responsavel.lower())

        if termo_sem_acentos in titulo or termo_sem_acentos in nome_resp or termo == '':
            tarefas_list.append(tarefa_data)

    context = {
        'tarefas': tarefas_list,
        'funcionarios': funcionarios_list,
        'user': request.session.get('user'),
    }

    return render(request, 'estabelecer_acao/estabelecer_acao.html', context)

@login_required
def editar_acao(request, id):
    if request.method == 'POST':
        db = initialize_firebase()
        tarefa_ref = db.collection('tarefas').document(id)

        tarefa_ref.update({
            'nome_acao': request.POST.get('nomeAcao'),
            'desc_acao': request.POST.get('descAcao'),
            'respo_acao': request.POST.get('respAcao'),
            'urge_acao': request.POST.get('urgeAcao'),
        })

        return redirect('estabelecer_acao')

@login_required
@require_POST
def delete_acao(request):
    db = initialize_firebase()
    print("DELETE ACIONADO")
    tarefa_id = request.POST.get('id')
    print("ID recebido:", tarefa_id)
    if tarefa_id:
        db.collection('tarefas').document(tarefa_id).delete()
        print("Documento deletado")
    else:
        print("Nenhum ID recebido")
    return redirect('estabelecer_acao')


    


# CRUD Funcionarios

@login_required
def addFuncionarios(request):
    if request.method == 'POST':
        db = initialize_firebase()

        funcionarios_ref = db.collection("funcionarios")
        quantidade = len(list(funcionarios_ref.stream()))
        novo_id = str(quantidade + 1)

        doc_ref = db.collection("funcionarios").document(novo_id)
        doc_ref.set({
            "nome_funcionario": request.POST.get('nome'),
            "cargo_funcionario": request.POST.get('cargo'),
            "cpf_funcionario": request.POST.get('cpf'),
            "data_funcionario": request.POST.get('data'),
            "sexo_funcionario": request.POST.get('sexo'),
            "tel_funcionario": request.POST.get('tel'),
            "email_funcionario": request.POST.get('mail')
        })

        time.sleep(5)

        return redirect('funcionarios')
    else:
        return JsonResponse({"erro": "Método não permitido"}, status=405)

@login_required
def listFuncionarios_view(request):
    db = initialize_firebase()

    termo = request.GET.get('searchFuncionario', '').strip().lower()
    termo_sem_acentos = unidecode(termo)

    funcionarios_ref = db.collection('funcionarios')
    funcionarios = funcionarios_ref.stream()

    funcionarios_list = []
    for funcionario in funcionarios:
        funcionario_data = funcionario.to_dict()
        funcionario_data['id'] = funcionario.id

        nome = unidecode(funcionario_data.get('nome_funcionario', '').lower())
        cargo = unidecode(funcionario_data.get('cargo_funcionario', '').lower())
        cpf = unidecode(funcionario_data.get('cpf_funcionario', '').lower())

        if termo_sem_acentos in nome or termo_sem_acentos in cargo or termo_sem_acentos in cpf or termo == '':
            funcionarios_list.append(funcionario_data)

    page_number = request.GET.get('page', 1)
    paginator = Paginator(funcionarios_list, 6) 
    page_obj = paginator.get_page(page_number)

    return render(request, 'funcionarios/funcionarios.html', {
    'page_obj': page_obj,
    'funcionarios': page_obj.object_list,
    'paginator': paginator,
    'searchFuncionario': termo,
    'user': request.session.get('user')
})

@login_required
def editar_funcionario(request, id):
    if request.method == 'POST':
        db = initialize_firebase()
        tarefa_ref = db.collection('funcionarios').document(id)

        tarefa_ref.update({
            "nome_funcionario": request.POST.get('nome'),
            "cargo_funcionario": request.POST.get('cargo'),
            "cpf_funcionario": request.POST.get('cpf'),
            "data_funcionario": request.POST.get('data'),
            "sexo_funcionario": request.POST.get('sexo'),
            "tel_funcionario": request.POST.get('tel'),
            "email_funcionario": request.POST.get('mail')
        })

        return redirect('funcionarios')

@login_required
@require_POST
def delete_funcionario(request):
    db = initialize_firebase()
    print("DELETE ACIONADO")
    funcionarios_id = request.POST.get('id')
    print("ID recebido:", funcionarios_id)
    if funcionarios_id:
        db.collection('funcionarios').document(funcionarios_id).delete()
        print("Documento deletado")
    else:
        print("Nenhum ID recebido")
    return redirect('funcionarios')
    


def NavigationHistoryMiddleware(get_response):
    def middleware(request):
        response = get_response(request)

        # Ignorar caminhos estáticos ou ajax
        if request.path.startswith('/static') or request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return response

        if 'navigation_history' not in request.session:
            request.session['navigation_history'] = []

        view_name = request.resolver_match.view_name if request.resolver_match else None

        if view_name and view_name not in request.session['navigation_history']:
            request.session['navigation_history'].append(view_name)

        return response

    return middleware

@login_required
def caixa_view(request):
    db = initialize_firebase()

    # Recupera o carrinho da sessão (lista de dicts)
    carrinho = request.session.get('carrinho', [])

    if request.method == 'POST':
        codigo = request.POST.get('codigo_produto')  # campo do input no HTML

        if codigo:
            # Buscar pelo campo correto: "cod_produto"
            produtos_ref = db.collection('produtos').where('cod_produto', '==', codigo).limit(1).stream()
            produto_doc = next(produtos_ref, None)

            if produto_doc:
                produto_data = produto_doc.to_dict()

                # Verifica se o produto já está no carrinho
                encontrado = False
                for item in carrinho:
                    if item['codigo'] == codigo:
                        item['qtd'] += 1
                        item['subtotal'] = round(item['qtd'] * float(item['preco']), 2)
                        encontrado = True
                        break

                if not encontrado:
                    carrinho.append({
                        'codigo': codigo,
                        'nome': produto_data.get('nome_produto', 'Sem nome'),
                        'qtd': 1,
                        'preco': float(produto_data.get('preco_produto', 0)),
                        'subtotal': float(produto_data.get('preco_produto', 0)),
                    })

                request.session['carrinho'] = carrinho
                return redirect('caixa')

    # Calcula total
    total = round(sum(item['subtotal'] for item in carrinho), 2)

    return render(request, 'caixa/caixa.html', {
        'carrinho': carrinho,
        'total': f"{total:.2f}",
        'user': request.session.get('user'),
    })

def finalizar_venda(request):
    carrinho = request.session.get('carrinho', [])
    db = initialize_firebase()

    if carrinho:
        total = sum(item['preco'] * item['qtd'] for item in carrinho)

        # Salva a venda
        db.collection('vendas').add({
        'itens': carrinho,
        'total': total,
        'data': datetime.now(pytz.timezone('America/Sao_Paulo'))  # <- Aqui!
        })

        # Atualiza o estoque dos produtos vendidos
        for item in carrinho:
            codigo = item['codigo']
            qtd_vendida = item['qtd']

            produtos_ref = db.collection('produtos').where('cod_produto', '==', codigo).limit(1).stream()
            produto_doc = next(produtos_ref, None)

            if produto_doc:
                produto_ref = db.collection('produtos').document(produto_doc.id)
                produto_data = produto_doc.to_dict()
                qtd_atual = produto_data.get('qtd_total', 0)

                nova_qtd = max(qtd_atual - qtd_vendida, 0)  # evita estoque negativo

                produto_ref.update({'qtd_total': nova_qtd})

        # Limpa o carrinho após finalizar
        request.session['carrinho'] = []

    return redirect('caixa')


@login_required
def cancelar_venda(request):
    request.session['carrinho'] = []
    return redirect('caixa')