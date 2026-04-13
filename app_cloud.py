import streamlit as st
import pandas as pd
import plotly.express as px
import pyodbc
import os
import numpy as np
from dotenv import load_dotenv
from datetime import date, timedelta, datetime
import warnings

# Ignora avisos chatos do Pandas/SQLAlchemy no terminal
warnings.filterwarnings('ignore')

# 1. Carrega variáveis de ambiente (apenas se o arquivo existir localmente)
if os.path.exists(".env"):
    load_dotenv()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(
    page_title="Histórico de Pedidos e Produtos",
    page_icon="📊",
    layout="wide"
)

# --- FUNÇÕES AUXILIARES ---

def format_brl(value):
    """Formata float para moeda brasileira R$."""
    if pd.isna(value) or value is None:
        return '-'
    return f"R$ {value:,.2f}".replace(',', '_').replace('.', ',').replace('_', '.')

def format_int_br(value):
    """Formata inteiro com separador de milhar pt-BR (ponto)."""
    if pd.isna(value):
        return '-'
    return f"{value:,.0f}".replace(',', '.')

def calcular_status_recompra(df_cliente, data_referencia):
    if isinstance(data_referencia, date):
        data_referencia = datetime.combine(data_referencia, datetime.min.time())
        
    if df_cliente.empty:
        return "Sem dados", 0, 0
    
    datas_pedidos = sorted(df_cliente['DtPedido'].unique())
    ultimo_pedido = datas_pedidos[-1]
    
    # 1. Dias sem Comprar
    dias_sem_comprar = (data_referencia - ultimo_pedido).days
    
    # 2. Se tiver menos de 2 pedidos
    if len(datas_pedidos) < 2:
        return "Sem Recorrência", 0, dias_sem_comprar
    
    # 3. Cálculo do Ciclo
    diffs = [(datas_pedidos[i] - datas_pedidos[i-1]).days for i in range(1, len(datas_pedidos))]
    media_dias_recompra = sum(diffs) / len(diffs)
    
    status = "Em dia"
    if dias_sem_comprar > (media_dias_recompra * 1.5):
        status = "Atrasado ⚠️"
    
    return status, media_dias_recompra, dias_sem_comprar

def calcular_ciclo_produto(df_produto):
    datas = sorted(df_produto['DtPedido'].unique())
    if len(datas) < 2:
        return None
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    return sum(diffs) / len(diffs)

# --- FUNÇÃO DE MOCK DATA (DADOS PARA DEPLOY) ---
def gerar_dados_fake(cod_cliente, data_ini, data_fim):
    """Gera uma base de dados aleatória com a mesma estrutura do SQL."""
    np.random.seed(42) 
    dias_diff = (data_fim - data_ini).days
    if dias_diff <= 0: dias_diff = 1
    
    n_linhas = 150
    datas = [data_ini + timedelta(days=int(np.random.randint(0, dias_diff))) for _ in range(n_linhas)]
    
    df_fake = pd.DataFrame({
        'DtPedido': pd.to_datetime(datas),
        'NuPed': np.random.randint(200000, 200500, n_linhas),
        'CodProd': np.random.choice([156602, 163435, 195, 4421, 5500, 8820], n_linhas),
        'Produto': np.random.choice([
            'Ração Premium Gatos 10kg', 'Ração Cão Adulto Carne', 
            'Sachê Frango 85g', 'Biscoito Canino Sabor Carne', 
            'Areia Sanitária Especial', 'Shampoo Pet Neutro'
        ], n_linhas),
        'Fabric': np.random.choice(['PetBr', 'GatosS/A', 'DogMaster', 'BioPet'], n_linhas),
        'Categ': np.random.choice(['Alimentos', 'Petiscos', 'Higiene'], n_linhas),
        'Qtde': np.random.randint(1, 20, n_linhas),
        'CodClien': cod_cliente
        'ItemBonif': 0
    })
    
    # Simula o valor de venda (Preço unitário entre 15 e 150 reais)
    df_fake['VlrVdacomImp'] = df_fake['Qtde'] * np.random.uniform(15.0, 150.0, n_linhas)
    return df_fake

# --- CONEXÃO COM BANCO (COMPATIBILIDADE TOTAL) ---
@st.cache_data(ttl=300, show_spinner="Consultando histórico no banco de dados...")
def buscar_historico(cod_cliente, tipo_cliente, data_ini, data_fim):
    server = os.getenv("DB_SERVER")
    
    # SE NÃO HOUVER SERVIDOR DEFINIDO (NUVEM), USA DADOS FAKE
    if not server:
        return gerar_dados_fake(cod_cliente, data_ini, data_fim)

    database = os.getenv("DB_DATABASE")
    username = os.getenv("DB_UID")
    password = os.getenv("DB_PWD")
    
    # Verifica drivers
    drivers_instalados = pyodbc.drivers()
    driver_escolhido = "SQL Server" # Fallback (Antigo)
    usar_driver_moderno = False

    if "ODBC Driver 18 for SQL Server" in drivers_instalados:
        driver_escolhido = "ODBC Driver 18 for SQL Server"
        usar_driver_moderno = True
    elif "ODBC Driver 17 for SQL Server" in drivers_instalados:
        driver_escolhido = "ODBC Driver 17 for SQL Server"
        usar_driver_moderno = True
    elif "ODBC Driver 13 for SQL Server" in drivers_instalados:
        driver_escolhido = "ODBC Driver 13 for SQL Server"
        usar_driver_moderno = True
    
    conn_str = (
        f"DRIVER={{{driver_escolhido}}};SERVER={server};DATABASE={database};"
        f"UID={username};PWD={password};"
    )
    
    # Driver 18 exige certificado confiável ou ignorar validação
    if "Driver 18" in driver_escolhido:
        conn_str += "TrustServerCertificate=yes;"

    try:
        with pyodbc.connect(conn_str) as conn:
            
            # --- ESTRATÉGIA DE EXECUÇÃO ---
            if usar_driver_moderno:
                # Método Seguro (Placeholders ?) - Funciona em drivers novos
                query = "{CALL sp_createdbyMGR_JBP_HistCompIndexSemVend (?, ?, ?, ?)}"
                df = pd.read_sql_query(query, conn, params=(cod_cliente, tipo_cliente, data_ini, data_fim))
            else:
                # Método Compatibilidade (String Pura) - Para drivers antigos que dão erro HYC00
                # Convertemos as datas para string YYYYMMDD para o SQL entender
                d_ini_str = data_ini.strftime('%Y%m%d')
                d_fim_str = data_fim.strftime('%Y%m%d')
                
                # Montamos a string manualmente (F-String)
                query = f"EXEC sp_createdbyMGR_JBP_HistCompIndexSemVend '{cod_cliente}', '{tipo_cliente}', '{d_ini_str}', '{d_fim_str}'"
                
                # Executa sem 'params'
                df = pd.read_sql_query(query, conn)
            
            # Limpeza de nomes de colunas
            df.columns = df.columns.str.strip()
            rename_map = {'↓ DtPedido': 'DtPedido', 'VlrVdaComImp': 'VlrVdacomImp'}
            df.rename(columns=rename_map, inplace=True)

            # Conversão de Tipos
            if not df.empty:
                if 'DtPedido' in df.columns:
                    df['DtPedido'] = pd.to_datetime(df['DtPedido'])
                cols_num = ['Qtde', 'VlrVdacomImp', 'CodProd', 'NuPed', 'CodClien']
                for col in cols_num:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            return df

    except Exception as e:
        st.error(f"Erro de conexão (Driver: {driver_escolhido}): {e}")
        return pd.DataFrame()

# --- INTERFACE (SIDEBAR) ---
st.sidebar.header("🔍 Filtros de Consulta")

# Inputs Automáticos
cod_cliente = st.sidebar.number_input("Código do Cliente", min_value=1, value=28132, step=1)
tipo_cliente = st.sidebar.selectbox("Tipo", options=["UNICO", "GRUPO", "COLIGACAO"], index=0)

col_dt1, col_dt2 = st.sidebar.columns(2)
data_hoje = date.today()

# Intervalo padrão de 3 anos
data_inicio_padrao = data_hoje - timedelta(days=1095)
data_ini = col_dt1.date_input("Data Inicial", data_inicio_padrao)
data_fim = col_dt2.date_input("Data Final", data_hoje)

st.sidebar.markdown("---")

# --- LÓGICA PRINCIPAL (REATIVA) ---

df_raw = buscar_historico(cod_cliente, tipo_cliente, data_ini, data_fim)

if df_raw is not None and not df_raw.empty:
    
    # Copia para manipulação
    df = df_raw.copy()

    # ==============================================================================
    # 🛠️ AJUSTE DE QUANTIDADE PARA DISPLAYS (CONVERSÃO PARA UNIDADE REAL)
    # ==============================================================================
    multiplicadores_display = {
        156602: 8,
        156603: 8,
        163435: 18,
        163436: 18,
        163438: 20,
        163437: 20
    }

    for codigo, fator in multiplicadores_display.items():
        mascara = df['CodProd'] == codigo
        if mascara.any():
            df.loc[mascara, 'Qtde'] = df.loc[mascara, 'Qtde'] * fator
    # ==============================================================================

    # --- FILTROS DE VISUALIZAÇÃO ---
    st.sidebar.header("🌪️ Filtros de Visualização")
    
    # 1. Filtro de Fabricante
    if 'Fabric' in df.columns:
        lista_fabricantes = sorted(df['Fabric'].astype(str).unique())
        filtro_fabricante = st.sidebar.multiselect(
            "Fabricante",
            options=lista_fabricantes,
            placeholder="Selecione para filtrar..."
        )
        if filtro_fabricante:
            df = df[df['Fabric'].isin(filtro_fabricante)]

    # 2. Filtro de Categoria
    if 'Categ' in df.columns:
        lista_categorias = sorted(df['Categ'].astype(str).unique())
        filtro_categoria = st.sidebar.multiselect(
            "Categoria",
            options=lista_categorias,
            placeholder="Selecione para filtrar..."
        )
        if filtro_categoria:
            df = df[df['Categ'].isin(filtro_categoria)]

    # 3. Filtro de Nome
    filtro_nome_produto = st.sidebar.text_input("Nome do Produto (Contém)", placeholder="Ex: Whiskas, Pedigree...")
    if filtro_nome_produto:
        df = df[df['Produto'].astype(str).str.contains(filtro_nome_produto, case=False, na=False)]

    # 4. Filtro por Código
    filtro_produtos_str = st.sidebar.text_area("Cód. Produtos (Separe por vírgula)", placeholder="Ex: 195, 4421")
    if filtro_produtos_str:
        try:
            codigos_busca = [int(x) for x in filtro_produtos_str.replace(',', ' ').split() if x.strip().isdigit()]
            if codigos_busca:
                df = df[df['CodProd'].isin(codigos_busca)]
        except: pass

    # --- PREPARAÇÃO DOS DADOS ---
    cols_group = ['NuPed', 'DtPedido', 'CodProd', 'Produto', 'Fabric', 'Categ']
    cols_existentes = [c for c in cols_group if c in df.columns]
    
    df_consolidado = df.groupby(cols_existentes).agg({
        'Qtde': 'sum',
        'VlrVdacomImp': 'sum',
        'ItemBonif': 'max'
    }).reset_index()

    df_consolidado['VlrUnitario'] = df_consolidado.apply(
        lambda x: x['VlrVdacomImp'] / x['Qtde'] if x['Qtde'] > 0 else 0, axis=1
    )
    df_consolidado.sort_values(by=['DtPedido', 'NuPed'], ascending=False, inplace=True)

    # --- INÍCIO DASHBOARD ---
    st.header(f"Cliente: {cod_cliente} ({tipo_cliente})")
    
    qtd_registros = len(df)
    if qtd_registros < len(df_raw):
        st.caption(f"Exibindo {qtd_registros} registros (Filtrados de {len(df_raw)}) | Período: {data_ini} até {data_fim}")
    else:
        st.caption(f"Total de {qtd_registros} registros encontrados | Período: {data_ini} até {data_fim}")

    tab1, tab2, tab3 = st.tabs(["📈 Resumo & Gráficos", "📝 Histórico Detalhado", "🗓️ Ciclo de Compra"])

    # === TAB 1: RESUMO ===
    with tab1:
        total_comprado = df['VlrVdacomImp'].sum()
        qtd_pedidos = df['NuPed'].nunique()
        ticket_medio = total_comprado / qtd_pedidos if qtd_pedidos > 0 else 0
        status_recompra, media_dias, dias_sem_comprar = calcular_status_recompra(df, data_fim)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", format_brl(total_comprado))
        c2.metric("Pedidos", qtd_pedidos)
        c3.metric("Ticket", format_brl(ticket_medio))
        c4.metric("Status", status_recompra, delta=f"{dias_sem_comprar} dias sem comprar", delta_color="inverse")

        st.divider()

        col_g1, col_g2 = st.columns(2)
        st.divider()

        # ==========================================
        # LINHA 1: Evolução Mensal e Top Fabricantes
        # ==========================================
        col_g1, col_g2 = st.columns(2)
        
        with col_g1:
            dados_grafico = []
            df_mensal = df.groupby(pd.Grouper(key='DtPedido', freq='MS'))
            
            for mes, group in df_mensal:
                if group.empty: continue
                    
                total_vlr = group['VlrVdacomImp'].sum()
                total_qtd = group['Qtde'].sum()
                
                # Agrupa e pega o Top 10 Produtos do mês
                top_prods = group.groupby(['CodProd', 'Produto']).agg({
                    'VlrVdacomImp': 'sum',
                    'Qtde': 'sum'
                }).reset_index().sort_values('VlrVdacomImp', ascending=False).head(10)
                
                # Monta o cabeçalho do Tooltip
                texto_tooltip = f"<b>Mês/Ano:</b> {mes.strftime('%b/%Y')}<br>"
                texto_tooltip += f"<b>Total do Mês:</b> {format_brl(total_vlr)} | {format_int_br(total_qtd)} un<br><br>"
                texto_tooltip += "<b style='color: #4C9AFF;'>🏆 Top 10 Produtos:</b><br>"
                
                # Loop para adicionar os 10 produtos de forma compacta
                for _, p_row in top_prods.iterrows():
                    cod = int(p_row['CodProd'])
                    nome = str(p_row['Produto']).title()
                    # Limita o nome a 22 caracteres para a caixa não ficar gigante
                    if len(nome) > 22:
                        nome = nome[:20] + "..."
                    
                    vlr = format_brl(p_row['VlrVdacomImp'])
                    qtd = format_int_br(p_row['Qtde'])
                    
                    texto_tooltip += f"<span style='font-size: 11px; color: #aaa;'>[{cod}]</span> <b>{nome}</b><br>"
                    texto_tooltip += f"&nbsp;&nbsp;↳ {vlr} | {qtd} un<br>"
                    
                dados_grafico.append({
                    'DtPedido': mes,
                    'VlrVdacomImp': total_vlr,
                    'Tooltip': texto_tooltip
                })
                
            monthly = pd.DataFrame(dados_grafico)
            
            if not monthly.empty:
                fig = px.bar(monthly, x='DtPedido', y='VlrVdacomImp', title="Evolução Mensal",
                             color_discrete_sequence=['#3366CC'], text_auto='.2s',
                             custom_data=['Tooltip'])
                
                fig.update_traces(
                    hovertemplate="%{customdata[0]}<extra></extra>"
                )
                
                fig.update_layout(
                    yaxis_tickprefix="R$ ",
                    hoverlabel=dict(
                        bgcolor="#1E1E1E", # Fundo escuro para destacar as cores
                        font=dict(color="white", size=12),
                        bordercolor="#444",
                        align="left"
                    )
                )
                fig.update_xaxes(dtick="M1", tickformat="%b %Y")
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Sem dados suficientes para o gráfico de Evolução Mensal.")
        
        with col_g2:
            if 'Fabric' in df.columns:
                top_fab = df.groupby('Fabric')['VlrVdacomImp'].sum().reset_index().sort_values('VlrVdacomImp', ascending=True).tail(10)
                fig2 = px.bar(top_fab, x='VlrVdacomImp', y='Fabric', orientation='h', title="Top Fabricantes",
                              color_discrete_sequence=['#DC3912'], text_auto='.2s')
                fig2.update_traces(hovertemplate='<b>%{y}</b><br><b>Total:</b> R$ %{x:,.2f}<extra></extra>')
                fig2.update_layout(xaxis_tickprefix="R$ ")
                st.plotly_chart(fig2, use_container_width=True)


        # ==========================================
        # LINHA 2: Análise de Categorias e Produtos (Empilhados)
        # ==========================================
        st.markdown("---")
        st.markdown("### 🛒 Análise de Produtos e Categorias")

        # --- 1. HEATMAP (Mapa de Calor de Produtos) ---
        if 'Produto' in df.columns and 'CodProd' in df.columns:
            df_heat = df.copy()
            df_heat['Produto_Label'] = df_heat['CodProd'].astype(str) + " - " + df_heat['Produto']
            df_heat['Mes'] = df_heat['DtPedido'].dt.to_period('M')
            
            # Matriz 1: Faturamento
            heat_data = df_heat.pivot_table(index='Produto_Label', columns='Mes', values='VlrVdacomImp', aggfunc='sum').fillna(0)
            
            # Matriz 2: Quantidade
            qty_data = df_heat.pivot_table(index='Produto_Label', columns='Mes', values='Qtde', aggfunc='sum').fillna(0)
            
            # Filtra os Top 15 e ordena
            top_prods = heat_data.sum(axis=1).sort_values(ascending=False).head(15).index
            
            heat_data = heat_data.loc[top_prods].sort_index(axis=1)
            heat_data.columns = heat_data.columns.strftime('%b/%Y')
            
            qty_data = qty_data.loc[top_prods].sort_index(axis=1)
            
            # Gráfico Base
            fig3 = px.imshow(heat_data,
                             title="Sazonalidade e Volume: Top 15 Produtos x Meses",
                             labels=dict(x="", y="", color="Faturamento"),
                             aspect="auto",
                             text_auto='.2s',
                             color_continuous_scale="Blues")
            
            fig3.update_traces(
                customdata=qty_data.values,
                hovertemplate=(
                    "<b>Mês:</b> %{x}<br>"
                    "<b>Produto:</b> %{y}<br>"
                    "<b>Faturamento:</b> R$ %{z:,.2f}<br>"
                    "<b>Quantidade:</b> %{customdata:,.0f} un"
                    "<extra></extra>"
                )
            )
            
            for i, col in enumerate(heat_data.columns):
                if col.startswith('Jan'):
                    fig3.add_vline(
                        x=i - 0.5,
                        line_width=2,
                        line_dash="dot",
                        line_color="#111111", # Preto/Cinza bem escuro
                        layer="above"
                    )
            
            st.plotly_chart(fig3, use_container_width=True)


        st.divider()


        # --- 2. TREEMAP (Árvore de Produtos) - MODELO ANTIGO RESTAURADO ---
        if 'Categ' in df.columns and 'Produto' in df.columns:
            # Agrupa os dados
            df_tree = df.groupby(['Categ', 'CodProd', 'Produto']).agg({
                'VlrVdacomImp': 'sum',
                'Qtde': 'sum'
            }).reset_index()
            
            df_tree = df_tree[df_tree['VlrVdacomImp'] > 0]
            df_tree['Produto_Label'] = df_tree['CodProd'].astype(str) + " - " + df_tree['Produto']
            
            # Volta a calcular no Pandas para termos os dados de produto perfeitos
            total_fat_tree = df_tree['VlrVdacomImp'].sum()
            total_qtd_tree = df_tree['Qtde'].sum()
            df_tree['Perc_Fat'] = df_tree['VlrVdacomImp'] / total_fat_tree
            df_tree['Perc_Qtd'] = df_tree['Qtde'] / total_qtd_tree
            
            import plotly.express as px
            fig4 = px.treemap(df_tree,
                              path=[px.Constant("Total Comprado"), 'Categ', 'Produto_Label'],
                              values='VlrVdacomImp',
                              title="Representatividade por Produto (Faturamento e Quantidade)",
                              color='VlrVdacomImp',
                              color_continuous_scale="Blues",
                              custom_data=['Qtde', 'Perc_Fat', 'Perc_Qtd'])
            
            fig4.update_traces(
                textposition='middle center',
                texttemplate='<b>%{label}</b><br>R$ %{value:,.2s} (%{customdata[1]:.1%})<br>%{customdata[0]:,.0f} un (%{customdata[2]:.1%})',
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Faturamento: R$ %{value:,.2f} (%{customdata[1]:.1%})<br>"
                    "Quantidade: %{customdata[0]:,.0f} un (%{customdata[2]:.1%})"
                    "<extra></extra>"
                ),
                marker=dict(line=dict(color='#0E1117', width=3))
            )
            
            fig4.update_layout(
                margin=dict(t=40, l=10, r=10, b=10),
                height=650,
                hoverlabel=dict(bgcolor="#1E1E1E", font_size=13)
            )
            
            st.plotly_chart(fig4, use_container_width=True)


        st.divider()


        # --- 3. ANÁLISE DE CATEGORIAS (O Novo Gráfico) ---
        if 'Categ' in df.columns:
            st.markdown("### 📊 Performance por Categoria")
            
            # Agrupa tudo apenas por Categoria
            df_cat = df.groupby('Categ').agg({
                'VlrVdacomImp': 'sum',
                'Qtde': 'sum'
            }).reset_index()
            
            df_cat = df_cat[df_cat['VlrVdacomImp'] > 0]
            
            # Calcula os %
            tot_vlr_cat = df_cat['VlrVdacomImp'].sum()
            tot_qtd_cat = df_cat['Qtde'].sum()
            df_cat['Perc_Fat'] = df_cat['VlrVdacomImp'] / tot_vlr_cat
            df_cat['Perc_Qtd'] = df_cat['Qtde'] / tot_qtd_cat
            
            # Ordena do menor para o maior (para a maior barra ficar no topo do gráfico)
            df_cat = df_cat.sort_values('VlrVdacomImp', ascending=True)
            
            fig5 = px.bar(df_cat,
                          x='VlrVdacomImp',
                          y='Categ',
                          orientation='h',
                          title="Faturamento vs Volume por Categoria",
                          color_discrete_sequence=['#3366CC'],
                          custom_data=['Qtde', 'Perc_Fat', 'Perc_Qtd'])
            
            # Formata o texto para mostrar TUDO dentro (ou fora) da barra
            fig5.update_traces(
                texttemplate='<b>R$ %{x:,.2s}</b> (%{customdata[1]:.1%}) | <b>%{customdata[0]:,.0f} un</b> (%{customdata[2]:.1%})',
                textposition='auto',
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Faturamento: R$ %{x:,.2f} (%{customdata[1]:.1%})<br>"
                    "Quantidade: %{customdata[0]:,.0f} un (%{customdata[2]:.1%})"
                    "<extra></extra>"
                )
            )
            
            # Deixa o layout super limpo
            fig5.update_layout(
                xaxis_tickprefix="R$ ",
                yaxis_title="",
                xaxis_title="",
                height=max(400, len(df_cat) * 40),
                hoverlabel=dict(bgcolor="#1E1E1E", font_size=13)
            )
            
            st.plotly_chart(fig5, use_container_width=True)

    # === TAB 2: DETALHADO ===
    with tab2:
        st.markdown("##### Espelho dos Pedidos")
        
        df_display = df.copy()
        df_display.sort_values(by=['DtPedido', 'NuPed'], ascending=False, inplace=True)
        
        # Unitário Médio Ponderado
        total_valor_grupo = df_display.groupby(['NuPed', 'CodProd'])['VlrVdacomImp'].transform('sum')
        total_qtde_grupo = df_display.groupby(['NuPed', 'CodProd'])['Qtde'].transform('sum')
        
        df_display['VlrUnitario'] = total_valor_grupo / total_qtde_grupo
        df_display['VlrUnitario'] = df_display['VlrUnitario'].fillna(0)

        df_display['Data'] = df_display['DtPedido'].dt.strftime('%d/%m/%Y')
        
        cols_map = {
            'NuPed': 'Nº Pedido',
            'Data': 'Data',
            'CodProd': 'Cód.',
            'Produto': 'Produto',
            'Fabric': 'Fabric',
            'Categ': 'Categoria',
            'Qtde': 'Qtd',
            'VlrVdacomImp': 'Total',
            'VlrUnitario': 'Unit. Médio'
        }
        
        cols_view = [c for c in cols_map.keys() if c in df_display.columns]
        df_display = df_display[cols_view].rename(columns=cols_map)

        mapa = {p: i % 2 for i, p in enumerate(df_display['Nº Pedido'].unique())}
        def colorir(row):
            return ['background-color: rgba(70, 130, 180, 0.25)' if mapa.get(row['Nº Pedido']) == 1 else ''] * len(row)

        st.dataframe(
            df_display.style.apply(colorir, axis=1).format({
                'Total': format_brl,
                'Unit. Médio': format_brl,
                'Qtd': format_int_br,
                'Nº Pedido': '{:.0f}'
            }).hide(axis="index"),
            use_container_width=True,
            height=600
        )

    # === TAB 3: CICLO DE COMPRA ===
    with tab3:
        st.markdown("### 🗓️ Performance e Status de Recompra por Produto")
        
        lista_produtos_ciclo = []
        ref_dt = datetime.combine(data_fim, datetime.min.time()) if isinstance(data_fim, date) else data_fim
        
        for cod, dados_prod in df.groupby('CodProd'):
            qtd_total = dados_prod['Qtde'].sum()
            data_ultimo_pedido = dados_prod['DtPedido'].max()
            ultimo_df = dados_prod[dados_prod['DtPedido'] == data_ultimo_pedido]
            qtd_ultimo = ultimo_df['Qtde'].sum()
            cod_ped_ultimo = ultimo_df['NuPed'].iloc[0]
            produto_nome = dados_prod['Produto'].iloc[0]
            
            # Busca no df_consolidado onde o Produto e o Pedido batem
            # ==========================================
            busca_preco = df_consolidado[
                (df_consolidado['CodProd'] == cod) & 
                (df_consolidado['NuPed'] == cod_ped_ultimo)
            ]
            
            # Se encontrou, pega o primeiro valor, se não, retorna 0
            ultimo_preco = busca_preco['VlrUnitario'].values[0] if not busca_preco.empty else 0
            # ==========================================
            
            menor_preco = 0
            if 'VlrUnitario' in df_consolidado.columns:
                 precos = df_consolidado[df_consolidado['CodProd'] == cod]['VlrUnitario']
                 precos_validos = precos[precos > 0]
                 if not precos_validos.empty:
                     menor_preco = precos_validos.min()

            ciclo_dias = calcular_ciclo_produto(dados_prod)
            dias_sem_comprar = (ref_dt - data_ultimo_pedido).days
            atraso = dias_sem_comprar - ciclo_dias if (ciclo_dias and ciclo_dias > 0) else 0
            
            if dados_prod['DtPedido'].nunique() > 1:
                lista_produtos_ciclo.append({
                    'Cód.': cod,
                    'Produto': produto_nome,
                    'Atraso_Dias': atraso,
                    'Ciclo (dias)': ciclo_dias,
                    'Qtd. Total Hist.': qtd_total,
                    'Qtd. Últ. Pedido': qtd_ultimo,
                    'Menor Preço Pago': menor_preco,
                    'Último Preço Pago': ultimo_preco,
                    'Dt. Últ. Pedido': data_ultimo_pedido,
                    'Cód. Últ. Pedido': cod_ped_ultimo
                })

        df_show = pd.DataFrame(lista_produtos_ciclo)
        
        if not df_show.empty:
            def gerar_status(row):
                atraso = row['Atraso_Dias']
                if atraso > 30: return "🚨 URGENTE (+30 dias)"
                if atraso > 0: return "⚠️ ATRASADO"
                return "✅ EM DIA"

            df_show['Status'] = df_show.apply(gerar_status, axis=1)
            df_show.sort_values(['Atraso_Dias'], ascending=False, inplace=True)
            
            # ---> NOVO: Coluna inserida na ordem desejada
            cols_final = ['Status', 'Cód.', 'Produto', 'Atraso_Dias', 'Ciclo (dias)', 
                          'Qtd. Total Hist.', 'Qtd. Últ. Pedido', 'Menor Preço Pago', 
                          'Último Preço Pago', # <---
                          'Dt. Últ. Pedido', 'Cód. Últ. Pedido']
            
            cols_final = [c for c in cols_final if c in df_show.columns]
            
            df_show = df_show[cols_final].rename(columns={'Atraso_Dias': 'Dias de Atraso'})

            def colorir_status(val):
                if not isinstance(val, str): return ''
                if 'URGENTE' in val: return 'color: #D32F2F; font-weight: bold;'
                elif 'ATRASADO' in val: return 'color: #F57C00; font-weight: bold;'
                return 'color: #388E3C;'

            st.dataframe(
                df_show.style.applymap(colorir_status, subset=['Status']).format({
                    'Qtd. Total Hist.': format_int_br,
                    'Qtd. Últ. Pedido': format_int_br,
                    'Menor Preço Pago': lambda x: format_brl(x) if x > 0 else '-',
                    'Último Preço Pago': lambda x: format_brl(x) if x > 0 else '-',
                    'Dias de Atraso': '{:.0f}',
                    'Ciclo (dias)': '{:.0f}',
                    'Cód. Últ. Pedido': '{:.0f}'
                }).hide(axis="index"),
                use_container_width=True,
                height=600,
                column_config={
                    "Dt. Últ. Pedido": st.column_config.DateColumn(
                        "Dt. Últ. Pedido",
                        format="DD/MM/YYYY"
                    )
                }
            )
        else:
            st.info("Não há dados suficientes de recompra.")

else:
    st.info("Aguardando dados... Verifique o código do cliente e as datas.")
