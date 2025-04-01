import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime

import pandas as pd
import matplotlib.pyplot as plt
import gzip
from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle, KeepTogether
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from openai import OpenAI
from markdown2 import markdown as md_to_html
from bs4 import BeautifulSoup

# Configuration du logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# 🔧 Initialisation de Flask
app = Flask(__name__)
CORS(app)

# 🔐 Client OpenAI
client = OpenAI()

PDF_FOLDER = "./pdf_reports/"
os.makedirs(PDF_FOLDER, exist_ok=True)

# Dossier contenant les fichiers DVF (.csv.gz)
DVF_FOLDER = "./dvf_data/"

def normalize_columns(df):
    """
    Nettoie et renomme toutes les colonnes DVF + fusionne adresse + force les types.
    """
    # Normalisation des noms de colonnes
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    rename_map = {
        "valeur_fonciere": "valeur_fonciere",
        "surface_reelle_bati": "surface_reelle_bati",
        "date_mutation": "date_mutation",
        "type_local": "type_local",
        "code_postal": "code_postal",
        "adresse_nom_voie": "nom_voie",
        "adresse_numero": "numero_voie",
    }
    df = df.rename(columns=rename_map)

    # 🔐 Force type str + nettoyage
    if "code_postal" in df.columns:
        df["code_postal"] = df["code_postal"].apply(
            lambda x: str(int(float(x))).zfill(5) if pd.notna(x) and str(x).replace('.', '', 1).isdigit() else None
)
    if "numero_voie" in df.columns:
        df["numero_voie"] = df["numero_voie"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

    if "nom_voie" in df.columns:
        df["nom_voie"] = df["nom_voie"].astype(str).str.strip()

    if "numero_voie" in df.columns and "nom_voie" in df.columns:
        df["adresse"] = df["numero_voie"] + " " + df["nom_voie"]
    elif "nom_voie" in df.columns:
        df["adresse"] = df["nom_voie"]

    return df



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

def generate_estimation_section(prompt, min_tokens=800):
    logging.info("Génération de la section d'estimation avec OpenAI...")
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {
                "role": "system",
                "content": (
                    "Tu es un expert en immobilier en France. Ta mission est de rédiger un rapport d'analyse détaillé, synthétique et professionnel "
                    "pour un bien immobilier. Le rapport doit être limité à 5 pages d'analyse (hors pages de garde) et inclure :\n"
                    "1. Une introduction personnalisée reprenant les informations du client (civilité, prénom, nom, adresse, etc.).\n"
                    "2. Une comparaison des prix des biens récemment vendus dans le même secteur, avec des tableaux récapitulatifs (prix au m², rendement locatif en pourcentage, etc.).\n"
                    "3. Des prévisions claires sur l'évolution du marché à 5 et 10 ans.\n"
                    "4. Une description précise de la localisation du bien sur un plan (par exemple, coordonnées géographiques ou description détaillée de l'emplacement).\n"
                    "Utilise intelligemment les données fournies et ne te contente pas de les répéter. Sois synthétique et oriente ton analyse vers des recommandations pratiques."
                )
            },
            {"role": "user", "content": prompt}
        ],
        max_tokens=min_tokens,
        temperature=0.8,
    )
    logging.info("Section générée par OpenAI.")
    content = response.choices[0].message.content.strip()
    if not content.endswith(('.', '!', '?')):
        content += "."
    return markdown_to_elements(content)


def resize_image(image_path, output_path, target_size=(469, 716)):
    from PIL import Image as PILImage
    with PILImage.open(image_path) as img:
        img = img.resize(target_size, PILImage.LANCZOS)
        img.save(output_path)

### Fonction d'extraction DVF et création du tableau comparatif
def load_dvf_data_avance(form_data):
    try:
        start_time = time.time()
        code_postal = str(form_data.get("code_postal", "")).zfill(5)
        adresse = form_data.get("adresse", "").lower()
        type_bien = form_data.get("type_bien", "").capitalize()
        # 🔍 Récupération intelligente de la surface selon le type de bien
        surface_bien = 0
        try:
            if form_data.get("type_bien") == "maison":
                surface_bien = float(form_data.get("maison_surface", 0))
            elif form_data.get("type_bien") == "appartement":
                surface_bien = float(form_data.get("app_surface", 0))
            elif form_data.get("type_bien") == "terrain":
                surface_bien = float(form_data.get("terrain_surface", 0))
        except ValueError:
            logging.warning("⚠️ Surface invalide ou non renseignée, filtrage DVF large appliqué.")
            surface_bien = 0


        dept_code = code_postal[:2]
        file_path_gz = os.path.join(DVF_FOLDER, f"{dept_code}.csv.gz")
        file_path_csv = os.path.join(DVF_FOLDER, f"{dept_code}.csv")

        logging.info(f"Recherche du fichier DVF pour le département {dept_code}...")

        if os.path.exists(file_path_gz):
            logging.info(f"📂 Chargement du fichier GZ : {file_path_gz}")
            df = pd.read_csv(file_path_gz, sep=",", low_memory=False)
            logging.info("✅ Colonnes brutes : %s", df.columns.tolist())

        elif os.path.exists(file_path_csv):
            logging.info(f"📂 Chargement du fichier CSV : {file_path_csv}")
            df = pd.read_csv(file_path_csv, sep=",", low_memory=False)
            logging.info("✅ Colonnes brutes : %s", df.columns.tolist())

        else:
            logging.error(f"Aucun fichier trouvé pour le département {dept_code}.")
            return None, f"Aucun fichier trouvé pour le département {dept_code}."

        logging.info("🔍 Exemple brut code_postal (avant normalisation) : %s", df["code_postal"].dropna().astype(str).unique()[:10])

        # 🔄 Normalisation
        df = normalize_columns(df)
        logging.info("✅ Colonnes après normalisation : %s", df.columns.tolist())

        if "code_postal" in df.columns:
            df["code_postal"] = df["code_postal"].astype(str).str.strip().str.zfill(5)
            logging.info("🔍 code_postal après normalisation : %s", df["code_postal"].dropna().unique()[:10])

        if "adresse" in df.columns:
            logging.info("🔍 Exemple d'adresse après normalisation : %s", df["adresse"].dropna().unique()[:5])

        # 💡 Et le reste du filtrage...
        df = df[df["code_postal"] == code_postal]
        logging.info("📊 Lignes après filtrage type_local=%s : %d", type_bien, len(df))  # Sauvegarde avant le filtrage d'adresse
        df_initial = df.copy()

        if adresse:
            mots = adresse.lower().split()
            df = df[df["adresse"].notna()]
            df = df[df["adresse"].apply(lambda x: any(mot in x.lower() for mot in mots))]
            logging.info(f"📊 Lignes après filtrage adresse='{adresse}' : {len(df)}")

        if df.empty:
                logging.warning("⚠️ Aucune correspondance sur l’adresse, on garde tous les biens du code postal.")
                df = df_initial


        if "surface_reelle_bati" not in df.columns or "valeur_fonciere" not in df.columns:
            logging.error("❌ Colonnes 'surface_reelle_bati' ou 'valeur_fonciere' absentes !")
            return None, "Colonnes manquantes"

        df = df[(df["surface_reelle_bati"] > 10) & (df["valeur_fonciere"] > 1000)]

        if surface_bien > 0:
            df = df[df["surface_reelle_bati"].between(surface_bien * 0.7, surface_bien * 1.3)]

        df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
        df = df.sort_values(by="date_mutation", ascending=False)

        elapsed = time.time() - start_time
        logging.info(f"✅ Chargement DVF terminé en {elapsed:.2f}s ({len(df)} lignes après filtrage).")
        return df, None

    except Exception as e:
        logging.error(f"❌ Erreur dans load_dvf_data_avance: {str(e)}")
        return None, f"Erreur DVF : {str(e)}"


def get_dvf_comparables(form_data):
    try:
        df, erreur = load_dvf_data_avance(form_data)
        if erreur or df is None or df.empty:
            logging.warning("Aucune donnée DVF trouvée après filtrage.")
            return f"Données indisponibles pour cette estimation. Erreur : {erreur or 'Aucune donnée trouvée.'}"

        df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
        df = df.sort_values(by="date_mutation", ascending=False).head(10)

        table_md = "| Adresse | Ville | Type de bien | Surface (m²) | Prix (€) | Prix/m² (€) |\n"
        table_md += "|---|---|---|---|---|---|\n"
        for _, row in df.iterrows():
            adresse = row.get("adresse", "")
            ville = row.get("nom_commune", "N/A")
            type_local = row.get("type_local", "N/A")
            surface = row.get("surface_reelle_bati", 0)
            valeur = row.get("valeur_fonciere", 0)
            prix_m2 = row.get("prix_m2", 0)
            table_md += f"| {adresse} | {ville} | {type_local} | {surface:.0f} | {valeur:.0f} | {prix_m2:.0f} |\n"

        logging.info("Tableau comparatif DVF généré.")
        return f"Voici les 10 dernières transactions similaires pour ce secteur :\n\n{table_md}"
    except Exception as e:
        logging.error(f"Erreur dans get_dvf_comparables: {str(e)}")
        return f"Données indisponibles pour cette estimation. Erreur : {str(e)}"

def generate_dvf_chart(form_data):
    try:
        start_time = time.time()
        code_postal = str(form_data.get("code_postal", "")).zfill(5)
        if not code_postal or not code_postal.isdigit() or len(code_postal) < 2:
            logging.warning("Code postal invalide.")
            return None

        dept_code = code_postal[:2]
        dvf_path = os.path.join(DVF_FOLDER, f"{dept_code}.csv.gz")
        if not os.path.exists(dvf_path):
            logging.error(f"Fichier DVF non trouvé pour le département {dept_code}.")
            return None

        logging.info(f"Chargement du fichier DVF pour le graphique: {dvf_path}")
        df = pd.read_csv(dvf_path, compression="gzip", low_memory=False)  # 🧠 plus de sep buggué
        df = normalize_columns(df)

        if "code_postal" not in df.columns:
            logging.error("❌ La colonne 'code_postal' est absente du fichier après normalisation.")
            return None

        df["code_postal"] = df["code_postal"].str.strip()
        code_postal = str(form_data.get("code_postal", "")).zfill(5)
        type_bien = form_data.get("type_bien", "").capitalize()
        df = df[df["code_postal"] == code_postal]
        df = df[df["type_local"] == type_bien]

        df = df[df["type_local"].isin(["Appartement", "Maison"])]
        df = df[(df["surface_reelle_bati"] > 10) & (df["valeur_fonciere"] > 1000)]
        df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
        df["date_mutation"] = pd.to_datetime(df["date_mutation"], errors="coerce")
        df = df.dropna(subset=["date_mutation"])
        df["année"] = df["date_mutation"].dt.year
        prix_m2_par_annee = df.groupby("année")["prix_m2"].mean().round(0)

        plt.figure(figsize=(8, 5))
        prix_m2_par_annee.plot(kind="line", marker="o", title=f"Évolution du prix moyen au m² - {code_postal}")
        plt.ylabel("Prix moyen au m² (€)")
        plt.xlabel("Année")
        plt.grid(True)
        plt.tight_layout()

        tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        plt.savefig(tmp_img.name)
        plt.close()
        elapsed = time.time() - start_time
        logging.info(f"📈 Graphique DVF généré en {elapsed:.2f} secondes.")
        return tmp_img.name
    except Exception as e:
        logging.error(f"💥 Erreur dans generate_dvf_chart : {str(e)}")
        return None

from reportlab.lib.enums import TA_CENTER

def create_highlighted_box(text):
    styles = getSampleStyleSheet()
    box_style = ParagraphStyle(
        'BoxStyle',
        parent=styles['BodyText'],
        backColor=colors.whitesmoke,
        borderColor=colors.HexColor("#00C7C4"),
        borderWidth=1,
        borderPadding=6,
        spaceBefore=12,
        spaceAfter=12,
    )
    return [Paragraph(text, box_style)]

def colored_paragraph(text, bg_color="#e8f9f9"):
    styles = getSampleStyleSheet()
    p = ParagraphStyle(
        'ColoredPara',
        parent=styles['BodyText'],
        backColor=bg_color,
        borderPadding=4,
        leading=14
    )
    return Paragraph(text, p)

def center_image(image_path, width=400, height=300):
    img = Image(image_path, width=width, height=height)
    img.hAlign = 'CENTER'
    return img

@app.route("/generate_estimation", methods=["POST"])
def generate_estimation():
    try:
        form_data = request.json
        logging.info("Début de la génération synchrone du rapport...")
        name = form_data.get("nom", "Client")
        city = form_data.get("quartier", "Non spécifié")
        adresse = form_data.get("adresse", "Non spécifiée")

        filename = os.path.join(PDF_FOLDER, f"estimation_{name.replace(' ', '_')}.pdf")
        doc = SimpleDocTemplate(filename, pagesize=A4,
                                topMargin=2*cm, bottomMargin=2*cm,
                                leftMargin=2*cm, rightMargin=2*cm)
        elements = []

        # Page de garde
        covers = ["static/cover_image.png", "static/cover_image1.png"]
        resized = []
        for img_path in covers:
            if os.path.exists(img_path):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    resize_image(img_path, tmp.name)
                    resized.append(tmp.name)
        logging.info("Page de garde préparée.")
        elements.append(Image(resized[0], width=469, height=716))
        elements.append(PageBreak())
    

        # Sections manuelles
                # Nouvelle structure logique et pro du rapport
        # Sections manuelles
        # Nouvelle structure logique et pro du rapport
        sections = [
            ("Résumé des données du questionnaire", resume_data),

            ("Introduction et Détails du bien", 
             f"Client : {form_data.get('civilite', '')} {form_data.get('prenom', '')} {form_data.get('nom', '')}, "
             f"domicilié(e) à {form_data.get('adresse_personnelle', '')} ({form_data.get('code_postal', '')}).\n"
             f"Email : {form_data.get('email', '')}, téléphone : {form_data.get('telephone', '')}.\n\n"
             f"Type de bien : {form_data.get('type_bien', '')}, superficie : {form_data.get('app_surface') or form_data.get('maison_surface') or form_data.get('terrain_surface')} m².\n"
             f"État général : {form_data.get('etat_general', '')}, travaux : {form_data.get('travaux_recent', '')} ({form_data.get('travaux_details', '')}), "
             f"problèmes : {form_data.get('problemes', '')}.\n"
             f"Équipements : {form_data.get('equipement_cuisine', '')}, électroménagers : {form_data.get('electromenager', '')}, sécurité : {form_data.get('securite', '')}.\n"
             f"DPE : {form_data.get('dpe', '')}, orientation : {form_data.get('orientation', '')}, vue : {form_data.get('vue', '')}."),

            ("Analyse des Données DVF", 
             "Voici les données comparatives extraites du fichier DVF officiel. Utilise **ces données comme base prioritaire pour l’estimation** et **ne les ignore jamais**. "
             "Tu trouveras un tableau récapitulatif des dernières ventes similaires, suivi d’un graphique des prix au m² sur les dernières années."),

            ("Environnement & Quartier", 
             f"Adresse : {form_data.get('adresse', '')}, quartier : {form_data.get('quartier', '')}.\n"
             f"Atouts : {form_data.get('atouts_quartier', '')}.\n"
             f"Commodités : commerces ({form_data.get('distance_commerces', '')}), écoles primaires ({form_data.get('distance_primaires', '')}), secondaires ({form_data.get('distance_secondaires', '')}).\n"
             f"Projets à venir : {form_data.get('developpement', '')}, circulation : {form_data.get('circulation', '')}."),

            ("Estimation & Analyse IA", 
             f"Estime la valeur réelle de ce bien (fourchette en €) en t'appuyant **exclusivement** sur les données DVF et les réponses ci-dessus.\n"
             f"Historique : temps sur le marché ({form_data.get('temps_marche', '')}), offres : {form_data.get('offres', '')}, "
             f"raison de vente : {form_data.get('raison_vente', '')}.\n"
             f"Prix similaires : {form_data.get('prix_similaires', '')}, prix visé : {form_data.get('prix', '')} (négociable : {form_data.get('negociation', '')})."),

            ("Analyse prédictive et Recommandations", 
             f"📈 **Prévision** : Évolution potentielle du prix sur 5 à 10 ans dans la zone de {form_data.get('quartier', '')}, selon projets locaux et marché.\n\n"
             f"✅ **Recommandations** :\n"
             f"Occupation actuelle : {form_data.get('occupe', '')}, dettes : {form_data.get('dettes', '')}, charges : {form_data.get('charges_fixes', '')}.\n"
             f"Contraintes : {form_data.get('contraintes', '')}, documents : {form_data.get('documents', '')}, conditions spéciales : {form_data.get('conditions', '')}.\n")
]


        for title, prompt in sections:
            add_section_title(elements, title)
            section = generate_estimation_section(prompt)
            elements.extend(section)
            elements.append(PageBreak())
        logging.info("Toutes les sections principales sont ajoutées.")


        # Page de fin
        if len(resized) > 1:
            elements.append(Image(resized[1], width=469, height=716))
        logging.info("Page de fin ajoutée.")

        doc.build(elements)
        logging.info("PDF généré avec succès.")
        return send_file(filename, as_attachment=True)

    except Exception as e:
        logging.error(f"Erreur dans generate_estimation: {str(e)}")
        return jsonify({"error": str(e)}), 500

# ==============================
# Endpoints pour génération asynchrone avec faux curseur et intégration DVF
# ==============================
progress_map = {}  # job_id -> progression (0-100)
results_map = {}   # job_id -> chemin du PDF généré

def generate_estimation_background(job_id, form_data):
    try:
        logging.info(f"Démarrage de la génération asynchrone pour job {job_id}...")
        progress_map[job_id] = 0

        name = form_data.get("nom", "Client")
        signature = f"{form_data.get('civilite', '')} {form_data.get('prenom', '')} {form_data.get('nom', '')}"
        filename = os.path.join(PDF_FOLDER, f"estimation_{name.replace(' ', '_')}_{job_id}.pdf")

        doc = SimpleDocTemplate(filename, pagesize=A4,
                                topMargin=2*cm, bottomMargin=2*cm,
                                leftMargin=2*cm, rightMargin=2*cm)
        elements = []
        styles = getSampleStyleSheet()
        progress_map[job_id] = 10

        # ✅ 1. Page de garde
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
        progress_map[job_id] = 20

        # ✅ 2. Résumé du questionnaire COMPLET
        add_section_title(elements, "Résumé du Questionnaire")
        résumé = ""
        for key, value in form_data.items():
            if isinstance(value, str) and value.strip():
                label = key.replace("_", " ").capitalize()
                résumé += f"- {label} : {value.strip()}\n"
        elements.append(Paragraph(résumé.strip().replace("\n", "<br/>"), styles['BodyText']))
        elements.append(PageBreak())
        progress_map[job_id] = 30

        # ✅ 3. Introduction personnalisée
        add_section_title(elements, "Introduction")
        intro_prompt = (
            f"Rédige une introduction professionnelle et synthétique pour {signature}, concernant l'estimation de son bien situé à "
            f"{form_data.get('adresse')} ({form_data.get('code_postal')}). Ce rapport se base uniquement sur les données fournies "
            "Dans le questionnaire et les données DVF."

        )
        elements.extend(generate_estimation_section(intro_prompt, min_tokens=300))
        progress_map[job_id] = 40

        # ✅ 4. Analyse des Données DVF
        add_section_title(elements, "Analyse des Données DVF")
        dvf_table_md = get_dvf_comparables(form_data)
        dvf_elements = markdown_to_elements(dvf_table_md)
        elements.append(KeepTogether(dvf_elements))

        dvf_chart_path = generate_dvf_chart(form_data)
        if dvf_chart_path:
            elements.append(Spacer(1, 12))
            elements.append(center_image(dvf_chart_path, width=400, height=300))
            elements.append(Paragraph("Évolution du prix moyen au m²", styles['Heading3']))
        elements.append(PageBreak())
        progress_map[job_id] = 60

        # ✅ 5. Estimation & Analyse – basée uniquement sur DVF + formulaire
        add_section_title(elements, "Estimation & Analyse")
        prenom_nom = f"{form_data.get('civilite', '')} {form_data.get('prenom', '')} {form_data.get('nom', '')}".strip()
        estimation_prompt = (
            f"Tu es un expert immobilier. En te basant uniquement sur :\n"
            f"- les données DVF précédemment listées (prix/m², surface, type de bien),\n"
            f"- les caractéristiques du bien ({form_data.get('type_bien', '')}, "
            f"{form_data.get('app_surface') or form_data.get('maison_surface') or form_data.get('terrain_surface', '')} m², "
            f"état : {form_data.get('etat_general', '')}, quartier : {form_data.get('quartier', '')}),\n"
            f"- l'historique (marché : {form_data.get('temps_marche', '')}, offres : {form_data.get('offres', '')}, "
            f"raison de vente : {form_data.get('raison_vente', '')}),\n"
            f"- et le prix visé ({form_data.get('prix', '')} €),\n\n"
            f"Fournis une estimation réaliste sous forme de fourchette de prix en euros (ex: entre 270 000 € et 290 000 €).\n"
            f"⚠️ Tu dois impérativement donner des chiffres crédibles basés sur les ventes DVF comparables.\n"
            f"Puis rédige une analyse synthétique (maximum 2 paragraphes), sans débuter par 'Madame, Monsieur' ni terminer par une signature."
        )



        elements.extend(generate_estimation_section(estimation_prompt, min_tokens=600))
        elements.append(PageBreak())
        progress_map[job_id] = 80

        # ✅ 6. Conclusion & Recommandations – claire et synthétique sans fourchette de prix
        add_section_title(elements, "Conclusion & Recommandations")
        conclusion_prompt = (
            f"Rédige une conclusion synthétique pour {prenom_nom} avec uniquement :\n"
            f"- Des **recommandations concrètes** sur la stratégie de vente (mise en valeur, timing, négociation).\n"
            f"- Une **prévision du marché** local à 5 ou 10 ans (courte et réaliste).\n"
            f"⚠️ **N'inclus pas** de fourchette de prix, **pas de tableau**, **pas de rappel de l’analyse précédente**.\n"
            f"Ne commence pas par une formule comme 'Cher...' et ne termine pas par un nom.\n"
            f"Termine par une **phrase complète bien rédigée**, sans 'Cordialement'."
        )


        elements.extend(generate_estimation_section(conclusion_prompt, min_tokens=400))

        # ✅ 7. Page de fin + cordialement
        if len(resized) > 1:
           elements.append(PageBreak())
           elements.append(Image(resized[1], width=469, height=716))

        # Ajouter "Cordialement" en toute fin du rapport
        elements.append(Spacer(1, 24))
        elements.append(Paragraph("Cordialement,", getSampleStyleSheet()["BodyText"]))

        progress_map[job_id] = 95
        doc.build(elements)
        results_map[job_id] = filename
        progress_map[job_id] = 100
        logging.info(f"✅ Rapport finalisé pour job {job_id}")


    except Exception as e:
        logging.error(f"Erreur dans generate_estimation_background: {str(e)}")
        progress_map[job_id] = -1
        results_map[job_id] = None



@app.route("/start_estimation", methods=["POST"])
def start_estimation():
    form_data = request.json or {}
    job_id = str(uuid.uuid4())
    logging.info(f"Démarrage du job asynchrone {job_id}...")
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

@app.route("/")
def home():
    return "✅ API d’estimation immobilière opérationnelle !"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logging.info(f"✅ Démarrage de l'API sur le port {port}")
    app.run(host="0.0.0.0", port=port)
