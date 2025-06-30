import os
import traceback
import psycopg2
import mercadopago

from flask import Flask, render_template, request, redirect, jsonify
from flask_mail import Mail, Message

app = Flask(__name__)

# Variáveis de ambiente obrigatórias
MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

if not MP_ACCESS_TOKEN or not MAIL_USERNAME or not MAIL_PASSWORD:
    raise RuntimeError("Variáveis de ambiente obrigatórias não configuradas.")

# Configuração SDK Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Configuração Flask-Mail (Mailtrap)
app.config.update(
    MAIL_SERVER='sandbox.smtp.mailtrap.io',
    MAIL_PORT=587,
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_USE_TLS=True,
    MAIL_USE_SSL=False
)
mail = Mail(app)

def criar_tabelas():
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
            nome TEXT NOT NULL,
            endereco TEXT,
            telefone TEXT NOT NULL,
            nome_dirigente TEXT,
            telefone_dirigente TEXT,
            remedio_controlado BOOLEAN,
            nome_remedio TEXT,
            horario_remedio TEXT,
            deficiencia_locomocao BOOLEAN,
            detalhes_deficiencia TEXT,
            condicao_mental BOOLEAN,
            detalhes_condicao_mental TEXT,
            batismo BOOLEAN,
            comunhao BOOLEAN,
            crisma BOOLEAN,
            casamento BOOLEAN,
            payment_id TEXT,
            payment_status TEXT
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS responsaveis (
            id SERIAL PRIMARY KEY,
            inscricao_id INTEGER NOT NULL REFERENCES inscricoes(id) ON DELETE CASCADE,
            nome TEXT NOT NULL,
            endereco TEXT,
            telefone TEXT
        );
    """)

    conn.commit()
    cursor.close()
    conn.close()

# Criar as tabelas ao iniciar (pode rodar só uma vez ou garantir idempotência)
criar_tabelas()

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST'),
        port=os.environ.get('DB_PORT'),
        database=os.environ.get('DB_NAME'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD')
    )

def salvar_inscricao(form):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Inserir cursista (inscricao)
    cursor.execute("""
        INSERT INTO inscricoes (
            nome, endereco, telefone,
            nome_dirigente, telefone_dirigente,
            remedio_controlado, nome_remedio, horario_remedio,
            deficiencia_locomocao, detalhes_deficiencia,
            condicao_mental, detalhes_condicao_mental,
            batismo, comunhao, crisma, casamento
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (
        form.get("nome_cursista"),
        form.get("endereco_cursista"),
        form.get("telefone_cursista"),
        form.get("nome_dirigente"),
        form.get("telefone_dirigente"),
        form.get("remedio_controlado") == "Sim",
        form.get("nome_remedio"),
        form.get("horario_remedio") if form.get("remedio_controlado") == "Sim" else None,
        form.get("deficiencia_locomocao") == "Sim",
        form.get("detalhes_deficiencia"),
        form.get("condicao_mental") == "Sim",
        form.get("detalhes_condicao_mental"),
        bool(form.get("batismo")),
        bool(form.get("comunhao")),
        bool(form.get("crisma")),
        bool(form.get("casamento"))
    ))

    inscricao_id = cursor.fetchone()[0]

    # Inserir responsáveis associados à inscrição
    nomes = form.getlist("nome_responsavel[]")
    enderecos = form.getlist("endereco_responsavel[]")
    telefones = form.getlist("telefone_responsavel[]")

    for nome, endereco, telefone in zip(nomes, enderecos, telefones):
        if nome.strip():  # Ignorar responsáveis sem nome
            cursor.execute("""
                INSERT INTO responsaveis (inscricao_id, nome, endereco, telefone)
                VALUES (%s, %s, %s, %s)
            """, (inscricao_id, nome.strip(), endereco.strip(), telefone.strip()))

    conn.commit()
    cursor.close()
    conn.close()

    return inscricao_id

def atualizar_pagamento(payment_id, status, inscricao_id=None):
    if not inscricao_id:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE inscricoes
        SET payment_id = %s, payment_status = %s
        WHERE id = %s
    """, (payment_id, status, inscricao_id))
    conn.commit()
    cursor.close()
    conn.close()

def enviar_email_confirmacao(nome, telefone):
    try:
        msg = Message(
            subject="Pagamento Aprovado - TLC",
            sender="inscricao@tlc.com",
            recipients=["devgbl34@outlook.com"]
        )
        msg.body = f"Pagamento aprovado para:\nNome: {nome}\nTelefone: {telefone}"
        mail.send(msg)
    except Exception as e:
        print(f"[ERRO] Email: {e}")
        traceback.print_exc()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            form = request.form
            if not form.get("nome_cursista") or not form.get("telefone_cursista"):
                return "Nome e telefone são obrigatórios", 400

            inscricao_id = salvar_inscricao(form)

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
                "external_reference": str(inscricao_id),
            }

            preference_response = sdk.preference().create(preference_data)

            if preference_response.get("status") != 201:
                return "Erro ao criar preferência de pagamento", 500

            init_point = preference_response["response"]["init_point"]
            return redirect(init_point)

        except Exception as e:
            print("[ERRO na rota / POST]:", e)
            traceback.print_exc()
            return f"Erro interno: {e}", 500

    return render_template("index.html")

@app.route("/obrigado")
def obrigado():
    return render_template("obrigado.html")

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    payment_id = data.get("id")
    topic = data.get("topic") or data.get("type")

    if topic == "payment" and payment_id:
        try:
            payment_info = sdk.payment().get(payment_id)
            if payment_info.get("status") != 200:
                return jsonify({"error": "Pagamento não encontrado"}), 404

            payment = payment_info["response"]
            status = payment.get("status")
            inscricao_id = payment.get("external_reference")

            if inscricao_id is None:
                return jsonify({"error": "Referência externa não encontrada"}), 400

            inscricao_id = int(inscricao_id)

            atualizar_pagamento(payment_id, status, inscricao_id)

            if status == "approved":
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT nome, telefone FROM inscricoes WHERE id = %s", (inscricao_id,))
                row = cursor.fetchone()
                cursor.close()
                conn.close()

                if row:
                    enviar_email_confirmacao(row[0], row[1])

        except Exception as e:
            print(f"[WEBHOOK ERROR]: {e}")
            traceback.print_exc()
            return jsonify({"error": "Falha interna"}), 500

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
