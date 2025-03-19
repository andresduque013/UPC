from flask import Flask, request, render_template, jsonify
import os
import re
import base64
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import requests

# Inicializar la aplicación Flask
app = Flask(__name__)

# Función para extraer números del nombre del archivo
def extract_upc_from_filename(filename):
    match = re.findall(r'\d+', filename)
    return ''.join(match) if match else None

# Ruta principal
@app.route("/")
def index():
    return render_template("index.html")

# Ruta para subir archivos
@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No se subió ningún archivo"}), 400
    
    file = request.files["file"]
    
    if file.filename == "":
        return jsonify({"error": "Nombre de archivo inválido"}), 400

    filename = file.filename
    upc_code = extract_upc_from_filename(filename)

    if not upc_code:
        return jsonify({"error": "No se encontró un código UPC en el nombre"}), 400

    return jsonify({"upc_code": upc_code})

# Ruta para obtener datos de Go-UPC y UPCItemDB
@app.route("/screenshot", methods=["POST"])
def take_screenshot():
    data = request.get_json()
    url = data.get("url")
    upc_code = data.get("upc_code")

    if not url or not upc_code:
        return jsonify({"error": "Datos insuficientes"}), 400

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)

    try:
        if "go-upc.com" in url:
            # Obtener datos de Go-UPC
            driver.get(url)
            driver.set_window_size(1200, 800)  # Ajustar el tamaño de la ventana
            element = driver.find_element(By.XPATH, '//*[@id="product-details"]')
            screenshot = element.screenshot_as_png
            driver.quit()

            return jsonify({
                "screenshot": f"data:image/png;base64,{base64.b64encode(screenshot).decode()}"
            })
        
        elif "upcitemdb.com" in url:
            # Obtener datos de UPCItemDB
            driver.get(url)
            try:
                # Verificar si hay un mensaje de error
                error_message = driver.find_element(By.XPATH, '//h2[contains(text(), "not a valid UPC")]')
                if error_message:
                    driver.quit()
                    return jsonify({"error": "Código UPC no válido en UPCItemDB"}), 400
            except NoSuchElementException:
                pass  # No hay mensaje de error, continuar

            try:
                # Esperar a que la página cargue completamente
                wait.until(EC.presence_of_element_located((By.XPATH, '/html/body/div[1]/div')))

                # Extraer el título
                title_element = driver.find_element(By.XPATH, '/html/body/div[1]/div/h2')
                title = title_element.text

                # Extraer la imagen
                image_element = driver.find_element(By.XPATH, '/html/body/div[1]/div/div[1]/div[1]/img')
                image_url = image_element.get_attribute("src")

                # Extraer la descripción
                description_element = driver.find_element(By.XPATH, '/html/body/div[1]/div/p')
                description = description_element.text

                driver.quit()

                return jsonify({
                    "screenshot": {
                        "title": title,
                        "description": description,
                        "image": image_url
                    }
                })
            except NoSuchElementException as e:
                driver.quit()
                return jsonify({"error": f"No se encontró el elemento en la página: {str(e)}"}), 500
            except TimeoutException:
                driver.quit()
                return jsonify({"error": "Tiempo de espera agotado al cargar la página"}), 500
        
        driver.quit()
        return jsonify({"error": "No se pudo capturar la página"}), 500
    except Exception as e:
        driver.quit()
        return jsonify({"error": str(e)}), 500

# Ruta para obtener la categoría de ChatGPT
@app.route("/get_chatgpt_category", methods=["POST"])
def get_chatgpt_category():
    data = request.get_json()
    upc_code = data.get("upc_code")

    if not upc_code:
        return jsonify({"error": "No se proporcionó un código UPC"}), 400

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 20)

    try:
        # Abrir ChatGPT
        driver.get("https://chat.openai.com/")
        
        # Esperar a que el usuario inicie sesión manualmente
        input("Por favor, inicia sesión en ChatGPT y presiona Enter para continuar...")

        # Escribir el prompt en ChatGPT
        prompt = f"Clasifica el producto con UPC {upc_code} en una de estas categorías: Grocery, Dairy, Frozen, Snack, Beverage, Non-food, Deli, Package Meat, Bakery, Seafood. Responde solo con el nombre de la categoría, siempre en ingles."
        wait.until(EC.element_to_be_clickable((By.TAG_NAME, "textarea"))).send_keys(prompt)
        
        # Enviar el prompt
        driver.find_element(By.XPATH, '//button[contains(text(), "Send")]').click()

        # Esperar la respuesta
        wait.until(EC.presence_of_element_located((By.XPATH, '//div[@class="response"]')))
        response = driver.find_element(By.XPATH, '//div[@class="response"]').text

        driver.quit()
        return jsonify({"category": response})
    except Exception as e:
        driver.quit()
        return jsonify({"error": str(e)}), 500

# Ruta para subir productos a XCirculars
@app.route("/upload_to_xcirculars", methods=["POST"])
def upload_to_xcirculars():
    if "file" not in request.files:
        return jsonify({"error": "No se subió ningún archivo"}), 400
    
    file = request.files["file"]
    upc_code = request.form.get("upc_code")

    if not upc_code:
        return jsonify({"error": "No se proporcionó un código UPC"}), 400

    # URL de la API de XCirculars
    xcirculars_url = "https://www.xcirculars.com/api/addProduct"

    # Preparar los datos para la solicitud POST
    files = {
        'image': (file.filename, file.stream, file.mimetype)
    }
    data = {
        'upc': upc_code
    }

    try:
        # Hacer la solicitud POST a la API de XCirculars
        response = requests.post(xcirculars_url, files=files, data=data)
        response_data = response.json()

        if response.status_code == 200 and response_data.get("success"):
            return jsonify({"success": True, "message": "Producto subido exitosamente a XCirculars"})
        else:
            return jsonify({"error": response_data.get("error", "Error desconocido al subir el producto")}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Iniciar la aplicación
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)