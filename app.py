import os
import traceback
import psycopg2
import mercadopago

from flask import Flask, render_template, request, redirect, jsonify
from flask_mail import Mail, Message

app = Flask(__name__)

# Configurações de ambiente obrigatórias
MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN')
MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')

if not MP_ACCESS_TOKEN or not MAIL_USERNAME or not MAIL_PASSWORD:
    raise RuntimeError("Variáveis de ambiente obrigatórias não configuradas.")

# SDK Mercado Pago
sdk = mercadopago.SDK(MP_ACCESS_TOKEN)

# Configuração Mailtrap
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
        CREATE TABLE IF NOT EXISTS cursistas (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            endereco TEXT,
            telefone TEXT,
            nome_dirigente TEXT,
            telefone_dirigente TEXT,
            remedio_controlado TEXT,
            nome_remedio TEXT,
            horario_remedio TEXT,
            deficiencia_locomocao TEXT,
            detalhes_deficiencia TEXT,
            condicao_mental TEXT,
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
            cursista_id INTEGER REFERENCES cursistas(id),
            nome TEXT,
            endereco TEXT,
            telefone TEXT
        );
    """)
    
    conn.commit()
    cursor.close()
    conn.close()

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

    # Responsáveis
    nomes = form.getlist("nome_responsavel[]")
    enderecos = form.getlist("endereco_responsavel[]")
    telefones = form.getlist("telefone_responsavel[]")

    for nome, endereco, telefone in zip(nomes, enderecos, telefones):
        cursor.execute("""
            INSERT INTO responsaveis (inscricao_id, nome, endereco, telefone)
            VALUES (%s, %s, %s, %s)
        """, (inscricao_id, nome, endereco, telefone))

    conn.commit()
    cursor.close()
    conn.close()
    return inscricao_id

def atualizar_pagamento(payment_id, status, inscricao_id=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    if inscricao_id:
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
        msg = Message("Pagamento Aprovado - TLC",
                      sender="inscricao@tlc.com",
                      recipients=["devgbl34@outlook.com"])
        msg.body = f"Pagamento aprovado para:\nNome: {nome}\nTelefone: {telefone}"
        mail.send(msg)
    except Exception as e:
        print(f"[ERRO] Email: {e}")
        traceback.print_exc()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
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
        return redirect(preference_response["response"]["init_point"])

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
            inscricao_id = int(payment.get("external_reference"))
        except Exception as e:
            print(f"[WEBHOOK ERROR]: {e}")
            return jsonify({"error": "Falha interna"}), 500

        atualizar_pagamento(payment_id, status, inscricao_id)

        if status == "approved":
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT nome, telefone FROM inscricoes WHERE id = %s", (inscricao_id,))
            row = cursor.fetchone()
            if row:
                enviar_email_confirmacao(row[0], row[1])
            cursor.close()
            conn.close()

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
