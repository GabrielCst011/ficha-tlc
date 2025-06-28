import mercadopago
import sqlite3
import os
import traceback
import psycopg2

from flask import Flask, render_template, request, redirect, jsonify
from flask_mail import Mail, Message

app = Flask(__name__)

# Validar variáveis de ambiente obrigatórias
MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

if not MP_ACCESS_TOKEN:
    raise RuntimeError("Variável de ambiente MP_ACCESS_TOKEN não configurada!")
if not MAIL_USERNAME or not MAIL_PASSWORD:
    raise RuntimeError("Variáveis de ambiente MAIL_USERNAME e MAIL_PASSWORD devem ser configuradas!")

# 🔑 SDK do Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# ✉️ Configuração do Mailtrap
app.config.update(
    MAIL_SERVER='sandbox.smtp.mailtrap.io',
    MAIL_PORT=587,
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_USE_TLS=True,
    MAIL_USE_SSL=False
)
mail = Mail(app)

# 📦 Banco SQLite - inicializa tabela para inscrições e pagamentos
def init_db():
    with sqlite3.connect("inscricoes.db") as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inscricoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                telefone TEXT,
                payment_id TEXT,
                payment_status TEXT
            )
        """)
        conn.commit()

init_db()

# Salva inscrição com dados básicos
def salvar_inscricao(form):
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST'),
        port=os.environ.get('DB_PORT'),
        database=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD')
    )
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inscricoes (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            telefone TEXT
        )
    """)
    cursor.execute("INSERT INTO inscricoes (nome, telefone) VALUES (%s, %s)", (
        form['nome_cursista'],
        form['telefone_cursista']
    ))
    conn.commit()
    cursor.close()
    conn.close()


# Atualiza status do pagamento e payment_id no banco
def atualizar_pagamento(payment_id, status, inscricao_id=None):
    with sqlite3.connect("inscricoes.db") as conn:
        cursor = conn.cursor()
        if inscricao_id:
            cursor.execute("""
                UPDATE inscricoes 
                SET payment_id = ?, payment_status = ?
                WHERE id = ?
            """, (payment_id, status, inscricao_id))
        else:
            # Atualiza a inscrição mais recente pendente (sem payment_id) para evitar múltiplas atualizações
            cursor.execute("""
                SELECT id FROM inscricoes WHERE payment_id IS NULL ORDER BY id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                id_para_atualizar = row[0]
                cursor.execute("""
                    UPDATE inscricoes 
                    SET payment_id = ?, payment_status = ?
                    WHERE id = ?
                """, (payment_id, status, id_para_atualizar))
        conn.commit()

# Envia e-mail de confirmação de pagamento aprovado
def enviar_email_confirmacao(nome, telefone):
    try:
        msg = Message("Pagamento Aprovado - TLC",
                      sender="inscricao@tlc.com",
                      recipients=["devgbl34@outlook.com"])
        msg.body = f"Pagamento aprovado para:\nNome: {nome}\nTelefone: {telefone}"
        mail.send(msg)
    except Exception as e:
        print(f"[ERRO] ao enviar email de confirmação: {e}")
        traceback.print_exc()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        form = request.form
        nome = form.get("nome_cursista")
        telefone = form.get("telefone_cursista")

        if not nome or not telefone:
            return "Nome e telefone são obrigatórios", 400

        # Salvar inscrição (status pendente)
        inscricao_id = salvar_inscricao(form)

        # Criar preferência de pagamento
        preference_data = {
            "items": [{
                "title": "Inscrição TLC 2025",
                "quantity": 1,
                "unit_price": 100.0,
            }],
            "back_urls": {
                "success": "https://ficha-tlc.onrender.com/obrigado",
                "failure": "https://ficha-tlc.onrender.com/falha",
                "pending": "https://ficha-tlc.onrender.com/pending"
            },
            "auto_return": "approved",
            # Usar external_reference para identificar inscrição
            "external_reference": str(inscricao_id),
        }

        preference_response = sdk.preference().create(preference_data)
        init_point = preference_response["response"]["init_point"]
        return redirect(init_point)

    return render_template("index.html")

@app.route("/obrigado")
def obrigado():
    return render_template("obrigado.html")

# Rota webhook para notificações Mercado Pago
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    print("[WEBHOOK] Dados recebidos:", data)

    topic = data.get('topic') or data.get('type')  # pode variar dependendo da API
    payment_id = data.get('id')

    if topic == "payment" and payment_id:
        # Consulta detalhes do pagamento via SDK
        try:
            payment_info = sdk.payment().get(payment_id)
            if payment_info.get("status") != 200:
                print(f"[WEBHOOK] Erro ao obter pagamento {payment_id}: {payment_info}")
                return jsonify({"error": "Pagamento não encontrado"}), 404
            payment = payment_info["response"]
            status = payment.get("status")
            external_reference = payment.get("external_reference")  # usado para identificar inscrição
        except Exception as e:
            print(f"[WEBHOOK] Erro ao consultar pagamento: {e}")
            traceback.print_exc()
            return jsonify({"error": "Erro interno"}), 500

        print(f"[WEBHOOK] Payment {payment_id} status: {status}, external_reference: {external_reference}")

        # Atualizar banco
        try:
            inscricao_id = int(external_reference) if external_reference and external_reference.isdigit() else None
        except:
            inscricao_id = None

        atualizar_pagamento(payment_id, status, inscricao_id)

        # Buscar dados para enviar email se pago
        if status == "approved":
            with sqlite3.connect("inscricoes.db") as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT nome, telefone FROM inscricoes WHERE payment_id = ?", (payment_id,))
                row = cursor.fetchone()
                if row:
                    nome, telefone = row
                    enviar_email_confirmacao(nome, telefone)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
