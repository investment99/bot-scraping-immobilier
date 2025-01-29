from flask import Flask, request, jsonify
import openai
import os
from dotenv import load_dotenv
import json
import traceback

load_dotenv()

app = Flask(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

cache = {}

@app.route('/search_real_estate', methods=['POST'])
def search_real_estate():
    """Génère des annonces basées sur les critères de recherche envoyés par le formulaire."""
    try:
        data = request.json
        print(f"📡 Recherche reçue : {data}")

        # Vérification des champs reçus
        city = data.get("city", "Non spécifié")
        property_type = data.get("property_type", "Non spécifié")
        surface_min = data.get("surface_min", "Non spécifié")
        surface_max = data.get("surface_max", "Non spécifié")
        price_min = data.get("price_min", "Non spécifié")
        price_max = data.get("price_max", "Non spécifié")

        # Création du prompt pour OpenAI
        prompt = f"""
        Je cherche des annonces immobilières avec ces critères :
        - Ville : {city}
        - Type de bien : {property_type}
        - Surface : entre {surface_min} et {surface_max} m²
        - Budget : entre {price_min} et {price_max} €

        Génère 5 annonces fictives avec :
        - Type de bien
        - Surface (m²)
        - Nombre de pièces
        - Prix (en €)
        - Localisation
        - Une description courte
        - Un lien fictif (ex: "https://annonce-immobiliere-fictive.com/annonce1")

        Répond uniquement avec du JSON strictement formaté.
        """

        # Appel à OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        raw_result = response["choices"][0]["message"]["content"].strip()
        print(f"🧠 Réponse brute OpenAI : {raw_result}")

        # Vérification et correction du JSON
        try:
            suggestions = json.loads(raw_result)
            return jsonify({"suggestions": suggestions}), 200
        except json.JSONDecodeError:
            print(f"❌ Erreur JSON OpenAI")
            return jsonify({"error": "Erreur lors de la génération des annonces"}), 500

    except Exception as e:
        print(f"❌ Erreur générale : {e}")
        traceback.print_exc()
        return jsonify({"error": f"Une erreur s'est produite: {str(e)}"}), 500


@app.route('/')
def home():
    return "✅ API Flask fonctionne correctement !"


if __name__ == "__main__":
    app.run(debug=True, port=5000)
