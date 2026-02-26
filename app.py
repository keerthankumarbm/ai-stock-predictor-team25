from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from database import db, init_app, User, Search
from werkzeug.security import generate_password_hash, check_password_hash
import yfinance as yf
import numpy as np
from datetime import datetime
from tensorflow.keras.models import load_model
from sklearn.preprocessing import MinMaxScaler
import os
import gdown
import pandas as pd 

# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret")

init_app(app)

with app.app_context():
    db.create_all()

# ---------------- MODEL DOWNLOAD ----------------
MODEL_URL = "https://drive.google.com/uc?id=1LMg8_eMwaes1MmOxA2IW0XcTzC6_LWFq"

if not os.path.exists("stock_model.h5"):
    print("Downloading ML model...")
    gdown.download(MODEL_URL, "stock_model.h5", quiet=False)

model = load_model("stock_model.h5")

# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("login"))

# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error="Username already exists!")

        hashed_password = generate_password_hash(password)
        new_user = User(username=username, password=hashed_password)

        db.session.add(new_user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')

# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            session['username'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Invalid Username or Password")

    return render_template('login.html')

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    username = session.get("username", "User")
    session.clear()
    return render_template("logout.html", username=username)

# ---------------- SAFE STOCK DOWNLOAD FUNCTION ----------------
def safe_download(stock):
    import requests
    api_key = os.environ.get("ALPHA_VANTAGE_KEY")

    # Always clean symbol first
    symbol = stock.upper().replace(".NS", "").replace(".BSE", "")

    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}.BSE&outputsize=compact&apikey={api_key}"

    response = requests.get(url)
    data = response.json()

    if "Time Series (Daily)" not in data:
        print("Alpha response:", data)
        return pd.DataFrame()

    time_series = data["Time Series (Daily)"]

    df = pd.DataFrame.from_dict(time_series, orient="index")
    df = df.astype(float)
    df = df.sort_index()
    df.rename(columns={"4. close": "Close"}, inplace=True)

    return df
# ---------------- PREDICTION ----------------
@app.route("/predict")
def predict():
    if "username" not in session:
        return jsonify({"error": "Not logged in"})

    stock = request.args.get("stock", "").upper().strip()
    print("Received stock:", stock)
    try:
        data = safe_download(stock)

        if data.empty:
            return jsonify({"error": f"No stock data for {stock}"})

        close_data = data[['Close']].values

        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(close_data)

        if len(scaled_data) < 60:
            return jsonify({"error": "Not enough data for prediction"})

        last_60 = scaled_data[-60:]
        X_test = np.reshape(last_60, (1, 60, 1))

        prediction = model.predict(X_test, verbose=0)
        predicted_price = float(scaler.inverse_transform(prediction)[0][0])

        # Save to DB
        new_search = Search(
            username=session["username"],
            stock=stock,
            price=predicted_price
        )
        db.session.add(new_search)
        db.session.commit()

        current_price = float(data['Close'].iloc[-1])
        change = predicted_price - current_price
        percent = (change / current_price) * 100

        signal = "UP" if change > 0 else "DOWN"

        if percent > 2:
            advice = "BUY"
        elif percent < -2:
            advice = "SELL"
        else:
            advice = "HOLD"

        return jsonify({
            "stock": stock,
            "predicted_price": round(predicted_price, 2),
            "current_price": round(current_price, 2),
            "change": round(change, 2),
            "percent": round(percent, 2),
            "signal": signal,
            "advice": advice
        })

    except Exception as e:
        return jsonify({"error": str(e)})

# ---------------- USER HISTORY ----------------
@app.route("/user_history")
def user_history():
    if "username" not in session:
        return jsonify([])

    rows = Search.query.filter_by(
        username=session["username"]
    ).order_by(Search.id.desc()).limit(5).all()

    history = []
    for r in rows:
        history.append({
            "stock": r.stock,
            "price": r.price,
            "time": r.time.strftime("%Y-%m-%d %H:%M:%S")
        })

    return jsonify(history)

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
