from django.shortcuts import render, redirect
from django.core.paginator import Paginator
from django.http import JsonResponse
import firebase_admin
from firebase_admin import firestore
from firebase_admin import credentials
from django.conf import settings
from django.views.decorators.http import require_POST
from django.contrib import messages
import time
from unidecode import unidecode
from functools import wraps
import json

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
           
            request.session['user'] = {'nome': username, 'cpf': cpf}
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
    return render(request, 'dashboard/dashboard.html', {'user': user})

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
    user = request.session.get('user')
    return render(request, 'historico/historico.html', {'user': user})

@login_required
def politica_view(request):
    user = request.session.get('user')
    return render(request, 'politica/politica.html', {'user': user})

@login_required
def relatorios_view(request):
    user = request.session.get('user')
    return render(request, 'relatorios/relatorios.html', {'user': user})

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
        data_fab = request.POST.get('dataFabProduto')
        data_val = request.POST.get('dataValProduto')
        categoria_produto = request.POST.get('categoriaProduto')

        try:
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
                "categoria": categoria_produto 
            })

            produto_novo = {
                "id": doc_ref.id,
                "cod_produto": cod_produto,
                "nome_produto": nome_produto,
                "preco_produto": preco_produto,
                "qtd_produto": qtd_produto,
                "lote_produto": lote_produto,
                "data_fabricacao": data_fab,
                "data_validade": data_val,
                "qtd_produtoPCx": qtd_produtoPCx,
                "categoria": categoria_produto
            }

            return JsonResponse({"success": True, "produto": produto_novo})

        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    return JsonResponse({"success": False, "error": "Método não permitido"}, status=405)
    
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
    }

    return render(request, 'produtos/produtos.html', context)

@login_required
def editar_produto(request, id):
    if request.method == 'POST':
        db = initialize_firebase()
        produto_ref = db.collection('produtos').document(id)

        produto_ref.update({
            'codigo': request.POST.get('codProduto'),
            'nome_produto': request.POST.get('nomeProduto'),
            'categoria': request.POST.get('categoriaProduto'),
            'preco_produto': float(request.POST.get('precoProduto')),
            'qtd_produtoPCx': int(request.POST.get('qntCxProduto', 0)),
            'qtd_produto': int(request.POST.get('qntPCxProduto', 0)),
            'lote_produto': request.POST.get('loteProduto'),
            'data_fabricacao': request.POST.get('dataFabProduto'),
            'data_validade': request.POST.get('dataValProduto'),
        })

        return redirect('produtos')

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

    termo = request.GET.get('searchAcao', '').strip().lower()
    termo_sem_acentos = unidecode(termo)

    funcionarios_ref = db.collection('funcionarios')
    funcionarios = funcionarios_ref.stream()

    funcionarios_dict = {}
    funcionarios_list = []
    for funcionario in funcionarios:
        func_data = funcionario.to_dict()
        func_data['id'] = funcionario.id
        funcionarios_list.append(func_data)
        funcionarios_dict[funcionario.id] = func_data.get('nome_funcionario', 'Desconhecido')

    tarefas_ref = db.collection('tarefas')
    tarefas = tarefas_ref.stream()

    tarefas_list = []
    for tarefa in tarefas:
        tarefa_data = tarefa.to_dict()
        tarefa_data['id'] = tarefa.id

        resp_id = tarefa_data.get('resp_acao')
        nome_responsavel = funcionarios_dict.get(resp_id, 'Desconhecido')
        tarefa_data['nome_responsavel'] = nome_responsavel

        titulo = unidecode(tarefa_data.get('nome_acao', '').lower())
        nome_resp = unidecode(nome_responsavel.lower())

        if termo_sem_acentos in titulo or termo_sem_acentos in nome_resp or termo == '':
            tarefas_list.append(tarefa_data)

    context = {
        'tarefas': tarefas_list,
        'funcionarios': funcionarios_list,
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
        'searchFuncionario': termo
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
    
