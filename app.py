import os
import shutil
import requests
import stat
import zipfile

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

CHROMIUM_URL = "https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.85/linux64/chrome-linux64.zip"
CHROMEDRIVER_URL = "https://storage.googleapis.com/chrome-for-testing-public/121.0.6167.85/linux64/chromedriver-linux64.zip"
CHROME_PATH = "/tmp/chrome-linux64/chrome"
CHROMEDRIVER_PATH = "/tmp/chromedriver-linux64/chromedriver"

def download_and_extract(url, extract_to):
    """Télécharge et extrait un fichier ZIP."""
    zip_path = extract_to + ".zip"
    response = requests.get(url, stream=True)
    with open(zip_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=128):
            f.write(chunk)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall("/tmp")
    os.chmod(extract_to, stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)  # Donner les permissions d'exécution
    os.remove(zip_path)

def setup_chromium():
    """Télécharge Chromium et ChromeDriver si nécessaire."""
    if not os.path.exists(CHROME_PATH):
        print("🔽 Téléchargement de Chromium...")
        download_and_extract(CHROMIUM_URL, CHROME_PATH)

    if not os.path.exists(CHROMEDRIVER_PATH):
        print("🔽 Téléchargement de ChromeDriver...")
        download_and_extract(CHROMEDRIVER_URL, CHROMEDRIVER_PATH)

def scrape_with_selenium(forum_url):
    try:
        setup_chromium()  # S'assurer que Chromium et ChromeDriver sont bien installés

        # Configuration spécifique pour Render
        chrome_options = Options()
        chrome_options.binary_location = CHROME_PATH
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-popup-blocking")
        chrome_options.add_argument("--window-size=1920x1080")

        # Lancer Chromium avec le bon WebDriver
        service = Service(CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        print("✅ Selenium a démarré avec succès sur Render.")

        driver.get(forum_url)
        driver.implicitly_wait(5)  # Attente pour éviter les blocages

        # Chercher et cliquer sur "Accepter les cookies"
        try:
            accept_button = driver.find_element(By.XPATH, "//button[contains(text(), 'Accepter') or contains(text(), 'J'accepte') or contains(text(), 'OK')]")
            accept_button.click()
            print("✅ Cookies acceptés avec succès")
            driver.implicitly_wait(2)
        except:
            print("⚠️ Aucun bouton de cookies détecté.")

        # Récupérer le HTML après acceptation des cookies
        page_source = driver.page_source
        driver.quit()
        return page_source

    except Exception as e:
        print(f"❌ Erreur Selenium sur Render: {str(e)}")
        return None
