import mercadopago
import sqlite3
import os

from flask import Flask, render_template, request, redirect
from flask_mail import Mail, Message


app = Flask(__name__)


# 🔑 SDK do Mercado Pago
sdk = mercadopago.SDK(os.environ.get('MP_ACCESS_TOKEN'))

# ✉️ Configuração do Mailtrap
app.config['MAIL_SERVER'] = 'sandbox.smtp.mailtrap.io'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
mail = Mail(app)

# 📦 Banco SQLite
def salvar_inscricao(form):
    conn = sqlite3.connect("inscricoes.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inscricoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT
        )
    """)
    cursor.execute("INSERT INTO inscricoes (nome, telefone) VALUES (?, ?)", (
        form['nome_cursista'],
        form['telefone_cursista']
    ))
    conn.commit()
    conn.close()

# 🌐 Rota principal
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        form = request.form
        nome = form["nome_cursista"]
        telefone = form["telefone_cursista"]

        # ✅ Salvar no banco
        salvar_inscricao(form)

        # ✅ Enviar e-mail
        try:
            msg = Message("Nova inscrição TLC",
                          sender="inscricao@tlc.com",
                          recipients=["devgbl34@outlook.com"])
            msg.body = f"Nome: {nome}\nTelefone: {telefone}"
            mail.send(msg)
        except Exception as e:
            print(f"[ERRO] ao enviar email: {e}")

        # ✅ Criar preferência de pagamento
        preference_data = {
            "items": [{
                "title": "Inscrição TLC 2025",
                "quantity": 1,
                "unit_price": 100.0,
            }],
            "back_urls": {
                "success": "https://ficha-tlc.onrender.com/obrigado",
                "failure": "https://ficha-tlc.onrender.com",
                "pending": "https://ficha-tlc.onrender.com"
            },
            "auto_return": "approved"
        }

        preference_response = sdk.preference().create(preference_data)
        return redirect(preference_response["response"]["init_point"])

    return render_template("index.html")

@app.route("/obrigado")
def obrigado():
    return render_template("obrigado.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))   
    app.run(host="0.0.0.0", port=port, debug=True)
