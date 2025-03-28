from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from datetime import datetime
import os
import tempfile
import threading
import time
import uuid
from openai import OpenAI
from markdown2 import markdown as md_to_html
from bs4 import BeautifulSoup

# 🔧 Initialisation de Flask
app = Flask(__name__)
CORS(app)

# 🔐 Client OpenAI
client = OpenAI()

PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

def markdown_to_elements(md_text):
    elements = []
    html_content = md_to_html(md_text, extras=["tables"])
    soup = BeautifulSoup(html_content, "html.parser")
    styles = getSampleStyleSheet()
    PAGE_WIDTH = A4[0] - 4 * cm

    for elem in soup.contents:
        if elem.name == "table":
            table_data = []
            for row in elem.find_all("tr"):
                row_data = [Paragraph(cell.get_text(strip=True), styles['BodyText']) for cell in row.find_all(["td", "th"])]
                table_data.append(row_data)
            col_count = len(table_data[0]) if table_data and table_data[0] else 1
            col_width = PAGE_WIDTH / col_count
            table_style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ])
            table = Table(table_data, colWidths=[col_width] * col_count, style=table_style)
            elements.append(table)
        elif elem.name:
            paragraph = Paragraph(elem.get_text(strip=True), styles['BodyText'])
            elements.append(paragraph)
            elements.append(Spacer(1, 12))
    return elements

def add_section_title(elements, title):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'SectionTitle',
        fontSize=16,
        fontName='Helvetica',
        textColor=colors.HexColor("#00C7C4"),
        alignment=1,
        spaceAfter=12,
        underline=True
    )
    elements.append(Paragraph(title, title_style))
    elements.append(Spacer(1, 12))

def generate_estimation_section(prompt, max_tokens=2000, temperature=0.8):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un expert en immobilier en France. Ta mission est de rédiger un rapport d'analyse détaillé, synthétique et professionnel pour un bien immobilier à partir des données fournies dans le questionnaire. "
                    "Le rapport doit être structuré sur 4 pages d'analyse (hors pages de garde) et divisé en 4 sections distinctes :\n\n"
                    "1. **Introduction personnalisée** : Récapitule les informations du client (civilité, prénom, nom, adresse, code postal, email, téléphone) et présente brièvement le contexte du bien.\n\n"
                    "2. **Analyse comparative** : Fournis une analyse détaillée avec un tableau comparatif des prix des biens récemment vendus dans le même secteur. Intègre des informations sur le quartier (proximité des métros, commerces, loisirs, etc.) et compare ces données avec la valeur actuelle estimée du bien.\n\n"
                    "3. **Localisation et environnement** : Décris précisément la localisation du bien, en incluant une référence à une image de plan ou des coordonnées géographiques précises, et analyse le quartier (commodités, transports, espaces verts, etc.).\n\n"
                    "4. **Analyse prédictive et recommandations** : Propose une analyse prédictive sur l'évolution du marché et la valeur du bien à 5 et 10 ans, avec des recommandations pratiques et structurées.\n\n"
                    "Utilise intelligemment les données fournies dans le questionnaire. Ne te contente pas de répéter les informations, mais crée un rapport structuré, détaillé et précis qui intègre un tableau comparatif et une analyse prédictive complète."
                )
            },
            {"role": "user", "content": prompt}
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return markdown_to_elements(response.choices[0].message.content)




def resize_image(image_path, output_path, target_size=(469, 716)):
    from PIL import Image as PILImage
    with PILImage.open(image_path) as img:
        img = img.resize(target_size, PILImage.LANCZOS)
        img.save(output_path)

@app.route("/generate_estimation", methods=["POST"])
def generate_estimation():
    try:
        form_data = request.json
        name = form_data.get("nom", "Client")
        city = form_data.get("quartier", "Non spécifié")
        adresse = form_data.get("adresse", "Non spécifiée")

        filename = os.path.join(PDF_FOLDER, f"estimation_{name.replace(' ', '_')}.pdf")
        doc = SimpleDocTemplate(filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
        elements = []

        # Page de garde
        covers = ["static/cover_image.png", "static/cover_image1.png"]
        resized = []
        for img_path in covers:
            if os.path.exists(img_path):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    resize_image(img_path, tmp.name)
                    resized.append(tmp.name)

        elements.append(Image(resized[0], width=469, height=716))
        elements.append(PageBreak())

        # Pour la version synchrone, nous conservons les sections définies manuellement
        sections = [
            ("Informations personnelles", 
             f"Commence le rapport par une introduction personnalisée en rappelant les informations suivantes : "
             f"{form_data.get('civilite')} {form_data.get('prenom')} {form_data.get('nom')}, domicilié(e) à {form_data.get('adresse_personnelle')}, "
             f"code postal {form_data.get('code_postal')}, email : {form_data.get('email')}, téléphone : {form_data.get('telephone')}. "
             f"Ensuite, présente brièvement la situation du client."),
            ("Informations générales sur le bien", f"Le bien est un(e) {form_data.get('type_bien')}. Voici les caractéristiques indiquées : {form_data}."),
            ("État général du bien", f"Voici les infos : état général = {form_data.get('etat_general')}, travaux récents = {form_data.get('travaux_recent')}, détails = {form_data.get('travaux_details')}, problèmes connus = {form_data.get('problemes')}."),
            ("Équipements et commodités", f"Équipements renseignés : cuisine/SDB = {form_data.get('equipement_cuisine')}, électroménager = {form_data.get('electromenager')}, sécurité = {form_data.get('securite')}."),
            ("Environnement et emplacement", f"Adresse : {form_data.get('adresse')} - Quartier : {form_data.get('quartier')} - Atouts : {form_data.get('atouts_quartier')} - Commerces : {form_data.get('distance_commerces')}."),
            ("Historique et marché", f"Temps sur le marché : {form_data.get('temps_marche')} - Offres : {form_data.get('offres')} - Raison : {form_data.get('raison_vente')} - Prix similaires : {form_data.get('prix_similaires')}."),
            ("Caractéristiques spécifiques", f"DPE : {form_data.get('dpe')} - Orientation : {form_data.get('orientation')} - Vue : {form_data.get('vue')}."),
            ("Informations légales", f"Contraintes : {form_data.get('contraintes')} - Documents à jour : {form_data.get('documents')} - Charges de copropriété : {form_data.get('charges_copro')}."),
            ("Prix et conditions de vente", f"Prix envisagé : {form_data.get('prix')} - Négociable : {form_data.get('negociation')} - Conditions particulières : {form_data.get('conditions')}."),
            ("Autres informations", f"Occupation : {form_data.get('occupe')} - Dettes : {form_data.get('dettes')} - Charges fixes : {form_data.get('charges_fixes')}."),
            ("Estimation IA", f"Estime le prix du bien situé à {form_data.get('adresse')} ({form_data.get('quartier')}), selon les infos fournies : {form_data}."),
            ("Analyse prédictive", f"Prédiction : comment évoluera ce bien ({form_data.get('type_bien')}) dans les 5 à 10 prochaines années dans le quartier de {form_data.get('quartier')} ?"),
            ("Recommandations IA", f"Que recommandes-tu à ce client pour mieux vendre ce bien ({form_data.get('type_bien')}) ?"),
        ]

        for title, prompt in sections:
            add_section_title(elements, title)
            section = generate_estimation_section(prompt)
            elements.extend(section)
            elements.append(PageBreak())

        # Page de fin
        if len(resized) > 1:
            elements.append(Image(resized[1], width=469, height=716))

        doc.build(elements)
        return send_file(filename, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ==============================
# Endpoints pour génération asynchrone avec faux curseur
# ==============================

progress_map = {}  # job_id -> progression (0-100)
results_map = {}   # job_id -> chemin du PDF généré

def generate_estimation_background(job_id, form_data):
    try:
        # Pour cette version asynchrone, on retire la découpe en sections.
        # On combine toutes les informations dans un unique prompt pour laisser l'IA gérer la structure (5 pages max)
        progress_map[job_id] = 0
        time.sleep(1)
        progress_map[job_id] = 40

        # Création du PDF et page de garde
        name = form_data.get("nom", "Client")
        filename = os.path.join(PDF_FOLDER, f"estimation_{name.replace(' ', '_')}_{job_id}.pdf")
        doc = SimpleDocTemplate(filename, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm, leftMargin=2*cm, rightMargin=2*cm)
        elements = []
        
        covers = ["static/cover_image.png", "static/cover_image1.png"]
        resized = []
        for img_path in covers:
            if os.path.exists(img_path):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    resize_image(img_path, tmp.name)
                    resized.append(tmp.name)
                    
        if resized:
            elements.append(Image(resized[0], width=469, height=716))
        elements.append(PageBreak())
        progress_map[job_id] = 70
        time.sleep(1)
        
        # Appel unique à OpenAI pour générer l'intégralité du rapport.
        # Le prompt contient toutes les informations du formulaire, et l'IA doit organiser le rapport en 5 pages maximum.
        combined_prompt = (
            f"Informations personnelles: {form_data.get('civilite')} {form_data.get('prenom')} {form_data.get('nom')}, "
            f"domicilié(e) à {form_data.get('adresse_personnelle')}, code postal {form_data.get('code_postal')}, "
            f"email: {form_data.get('email')}, téléphone: {form_data.get('telephone')}. "
            f"Informations générales sur le bien: le bien est un(e) {form_data.get('type_bien')}. Détails: {form_data}. "
            f"État général: {form_data.get('etat_general')}, travaux récents: {form_data.get('travaux_recent')}, "
            f"détails: {form_data.get('travaux_details')}, problèmes connus: {form_data.get('problemes')}. "
            f"Équipements et commodités: {form_data.get('equipement_cuisine')}, {form_data.get('electromenager')}, {form_data.get('securite')}. "
            f"Environnement et emplacement: {form_data.get('adresse')}, {form_data.get('quartier')}, atouts: {form_data.get('atouts_quartier')}, "
            f"commerces: {form_data.get('distance_commerces')}. "
            f"Historique et marché: {form_data.get('temps_marche')}, offres: {form_data.get('offres')}, "
            f"raison de vente: {form_data.get('raison_vente')}, prix similaires: {form_data.get('prix_similaires')}. "
            f"Caractéristiques spécifiques: {form_data.get('dpe')}, {form_data.get('orientation')}, {form_data.get('vue')}. "
            f"Informations légales: {form_data.get('contraintes')}, {form_data.get('documents')}, charges: {form_data.get('charges_copro')}. "
            f"Prix et conditions de vente: {form_data.get('prix')}, négociable: {form_data.get('negociation')}, conditions: {form_data.get('conditions')}. "
            f"Autres informations: {form_data.get('occupe')}, dettes: {form_data.get('dettes')}, charges fixes: {form_data.get('charges_fixes')}."
        )
        section = generate_estimation_section(combined_prompt)
        elements.extend(section)
        elements.append(PageBreak())
        progress_map[job_id] = 80
        time.sleep(1)
        
        # Page de fin
        if len(resized) > 1:
            elements.append(Image(resized[1], width=469, height=716))
        progress_map[job_id] = 90
        time.sleep(1)
        
        doc.build(elements)
        progress_map[job_id] = 100
        results_map[job_id] = filename
        
    except Exception as e:
        progress_map[job_id] = -1
        results_map[job_id] = None

@app.route("/start_estimation", methods=["POST"])
def start_estimation():
    form_data = request.json or {}
    job_id = str(uuid.uuid4())
    thread = threading.Thread(target=generate_estimation_background, args=(job_id, form_data))
    thread.start()
    return jsonify({"job_id": job_id})

@app.route("/progress", methods=["GET"])
def get_progress():
    job_id = request.args.get("job_id")
    if not job_id or job_id not in progress_map:
        return jsonify({"error": "Job introuvable"}), 404
    return jsonify({"progress": progress_map[job_id]})

@app.route("/download_estimation", methods=["GET"])
def download_estimation():
    job_id = request.args.get("job_id")
    if not job_id or job_id not in results_map:
        return jsonify({"error": "Job introuvable"}), 404
    pdf_path = results_map[job_id]
    if not pdf_path or not os.path.exists(pdf_path):
        return jsonify({"error": "PDF introuvable ou non généré"}), 404
    return send_file(pdf_path, as_attachment=True)

# ✅ Fin du fichier : routes de base pour test Render
@app.route("/")
def home():
    return "✅ API d’estimation immobilière opérationnelle !"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"✅ Démarrage de l'API sur le port {port}")
    app.run(host="0.0.0.0", port=port)
