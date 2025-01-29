from flask import Flask

app = Flask(__name__)

print("🚀 Lancement de l'application Flask...")

@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"

@app.route('/test')
def test():
    return "🚀 Route de test fonctionne !"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
