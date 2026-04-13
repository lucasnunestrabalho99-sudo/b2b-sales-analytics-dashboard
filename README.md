# 📊 B2B Sales & Repurchase Analytics Dashboard

Um dashboard interativo e robusto desenvolvido em Python (Streamlit) para monitorar o histórico de pedidos, analisar a performance de produtos e gerenciar o ciclo de recompra de clientes de forma automatizada.

## 🎯 Sobre o Projeto

No mercado B2B, entender a jornada de compra do cliente e antecipar a necessidade de reposição de estoque é um diferencial competitivo. Este projeto foi desenvolvido para conectar-se diretamente a um banco de dados SQL Server, processar históricos de vendas e traduzir esses dados em insights visuais acionáveis.

A principal inovação da ferramenta é o seu motor de cálculo de **Ciclo de Compra**, que identifica automaticamente padrões de consumo e emite alertas sobre clientes ou produtos que estão com atraso na renovação de pedidos.

## ✨ Principais Funcionalidades

* **Integração Direta com Banco de Dados:** Utiliza `pyodbc` para conectar-se a bases SQL Server, com suporte a drivers modernos e tratamento de compatibilidade.
* **Análise de Recompra (Churn Prevention):** Calcula o tempo médio de ciclo de cada produto e sinaliza o status (✅ Em Dia, ⚠️ Atrasado, 🚨 Urgente) com base na data do último pedido.
* **Métricas de Performance:** Cálculo automático de ticket médio, faturamento total, e top produtos/fabricantes do período filtrado.
* **Visualização de Dados Avançada:**
  * **Gráficos de Barra Empilhados:** Comparativo de faturamento vs volume por categoria.
  * **Mapas de Calor (Heatmaps):** Análise de sazonalidade mensal dos produtos mais vendidos.
  * **Espelho de Pedidos:** Tabela detalhada formatada dinamicamente para auditoria rápida.
* **Tratamento de Dados Específicos:** Lógica de conversão automática para multiplicadores de display (ajuste de embalagens para unidades reais de venda).

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** Python 3
* **Ambiente:** Anaconda
* **Interface e Web App:** Streamlit
* **Manipulação de Dados:** Pandas
* **Visualização:** Plotly (Express)
* **Banco de Dados:** SQL Server (`pyodbc`)
* **Gerenciamento de Variáveis:** `python-dotenv`

## 🚀 Como executar este projeto localmente

### 1. Clone o repositório
```bash
git clone [https://github.com/SEU_USUARIO/b2b-sales-analytics-dashboard.git](https://github.com/SEU_USUARIO/b2b-sales-analytics-dashboard.git)
cd b2b-sales-analytics-dashboard
```

### 2. Instale as dependências
Recomenda-se o uso do seu ambiente Anaconda. Com o ambiente ativado, instale os pacotes necessários:
```bash
pip install -r requirements.txt
```

### 3. Configure as Variáveis de Ambiente
Crie um arquivo chamado `.env` na raiz do projeto, usando o arquivo `.env.example` como base, e insira as credenciais do seu banco de dados SQL Server:
```env
DB_SERVER=endereco_do_servidor
DB_DATABASE=nome_do_banco
DB_UID=usuario
DB_PWD=senha
```
*Aviso: Certifique-se de que o arquivo `.env` esteja listado no seu `.gitignore` para não expor suas credenciais.*

### 4. Execute a aplicação
```bash
streamlit run app.py
```

## 🧠 Lógica do Ciclo de Recompra

O algoritmo do ciclo de recompra agrupa as compras por produto e calcula a diferença em dias entre os pedidos sequenciais. A média desses intervalos define o "Ciclo (dias)". 

Se a diferença entre a data atual e a data do último pedido for maior que o ciclo calculado, o sistema classifica o produto como "Atrasado". Se ultrapassar 30 dias do ciclo ideal, é classificado como "Urgente", permitindo que a equipe comercial aja ativamente para recuperar a venda.

---
