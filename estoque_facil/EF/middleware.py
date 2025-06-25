class HistoryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Inicializa lista se não existir
        history = request.session.get('history', [])

        # Adiciona o path atual, sem query string
        current_path = request.path

        # Evita duplicatas consecutivas
        if not history or history[-1] != current_path:
            history.append(current_path)

        # Limita tamanho da lista (exemplo 20 últimos)
        history = history[-20:]

        request.session['history'] = history

        response = self.get_response(request)
        return response