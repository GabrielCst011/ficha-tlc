from flask import Flask, render_template, request, redirect
import mercadopago
import os

app = Flask(__name__)

sdk = mercadopago.SDK("APP_USR-673838628377632-061116-53fc407b76ce738ff74227ed8d59e6e3-727080461")

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        nome = request.form["nome_cursista"]
        telefone = request.form["telefone_cursista"]

        preference_data = {
            "items": [{
                "title": "Inscrição TLC 2025",
                "quantity": 1,
                "unit_price": 100.0,
            }],
            "back_urls": {
                "success": "https://ficha-tlc.onrender.com/obrigado",
                "failure": "https://ficha-tlc.onrender.com",
                "pending": "https://ficha-tlc.onrender.com",
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
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)

