from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from tensorflow.keras.models import load_model
from tensorflow.keras import backend as K
from keras.saving import register_keras_serializable
from PIL import Image
import numpy as np
import io

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# Register custom loss if models were trained using it
@register_keras_serializable()
def balanced_binary_crossentropy(y_true, y_pred):
    epsilon = K.epsilon()
    y_pred = K.clip(y_pred, epsilon, 1.0 - epsilon)

    weight_0 = K.sum(1. - y_true)
    weight_1 = K.sum(y_true)
    beta = weight_0 / (weight_0 + weight_1)

    loss = -beta * y_true * K.log(y_pred) - (1 - beta) * (1 - y_true) * K.log(1 - y_pred)
    return K.mean(loss)

# Load category-specific models (3)
category_models = {
    "Weapon": load_model("models/best_weapon_model.keras", custom_objects={'balanced_binary_crossentropy': balanced_binary_crossentropy}),
    "Gore": load_model("models/best_gore_model.keras", custom_objects={'balanced_binary_crossentropy': balanced_binary_crossentropy}),
    "Explosive": load_model("models/best_explosive_model.keras", custom_objects={'balanced_binary_crossentropy': balanced_binary_crossentropy}),
}

# Load general models (2)
general_models = {
    "Custom CNN": load_model("models/custom_cnn_model.keras", custom_objects={'balanced_binary_crossentropy': balanced_binary_crossentropy}),
    "EfficientNet": load_model("models/efficientnet_model.keras", custom_objects={'balanced_binary_crossentropy': balanced_binary_crossentropy}),
}

def preprocess_image(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image = image.resize((256, 256))
    image_array = np.array(image) / 255.0
    image_array = np.expand_dims(image_array, axis=0)
    return image_array

@app.route("/")
def serve_index():
    return render_template("index.html")

@app.route("/predict", methods=["POST"])
def predict():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        image_bytes = file.read()
        image_array = preprocess_image(image_bytes)
    except Exception as e:
        return jsonify({"error": f"Invalid image file: {str(e)}"}), 400

    THRESHOLD = 0.27  # Your custom threshold

    votes = {"Safe": 0, "Prohibited": 0}

    # --- Step 1: Run category-specific models ---
    for model in category_models.values():
        pred = model.predict(image_array)[0][0]
        status = "Safe" if pred >= THRESHOLD else "Prohibited"
        votes[status] += 1

    # --- Step 2: Run general models ---
    for model in general_models.values():
        pred = model.predict(image_array)[0][0]
        status = "Safe" if pred >= THRESHOLD else "Prohibited"
        votes[status] += 1

    # --- Step 3: Majority Voting (total 5 models) ---
    final_status = "Prohibited" if votes["Prohibited"] >= 3 else "Safe"

    return jsonify({"status": final_status})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)