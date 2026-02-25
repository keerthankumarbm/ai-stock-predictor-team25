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
MODEL_URL = "https://drive.google.com/uc?id=1LMg8_eMwaes1MmOxA2IW0XcTzC6_LWFq"

if not os.path.exists("stock_model.h5"):
    print("Downloading ML model...")
    gdown.download(MODEL_URL, "stock_model.h5", quiet=False)

model = load_model("stock_model.h5")
# ---------------- APP SETUP ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback-secret")

init_app(app)

with app.app_context():
    db.create_all()

init_db()

# Load ML model once
model = load_model("stock_model.h5")


# ---------------- HOME ----------------
@app.route("/")
def home():
    return redirect(url_for("login"))


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET','POST'])
def login():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            if user:
                session['username'] = username
                return redirect(url_for('dashboard'))
            else:
                return render_template('login.html', error="Invalid Username or Password")

    return render_template('login.html')


# ---------------- REGISTER ----------------
@app.route('/register', methods=['GET','POST'])
def register():

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        hashed = generate_password_hash(password)
        new_user = User(username=username, password=hashed)
        db.session.add(new_user)
        db.session.commit()

        if success:
            return redirect(url_for('login'))
        else:
            return render_template('register.html', error="Username already exists!")

    return render_template('register.html')


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


# ---------------- PREDICTION ----------------
@app.route("/predict")
def predict():
    if "username" not in session:
        return jsonify({"error": "Not logged in"})

    stock = request.args.get("stock")

    try:
        data = yf.download(stock, period="3mo")

        if data.empty:
            return jsonify({"error": "No stock data"})

        close_data = data[['Close']].values

        scaler = MinMaxScaler(feature_range=(0, 1))
        scaled_data = scaler.fit_transform(close_data)

        last_60 = scaled_data[-60:]
        X_test = np.reshape(last_60, (1, 60, 1))

        prediction = model.predict(X_test)
        predicted_price = float(scaler.inverse_transform(prediction)[0][0])

        # save history with logged user
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
        if change > 0:
            signal = "UP"
        else:
            signal = "DOWN"

        # ---------- AI ADVICE ----------
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

@app.route("/history")
def history():
    if "username" not in session:
        return jsonify({"error": "Not logged in"})

    stock = request.args.get("stock")

    try:
        data = yf.download(stock, period="3mo")

        if data.empty:
            return jsonify({"error": "No stock data"})

        data.reset_index(inplace=True)

        # ---- CRITICAL FIX ----
        close_series = data["Close"]

        # If dataframe (multi-index) → take first column
        if hasattr(close_series, "columns"):
            close_series = close_series.iloc[:,0]

        dates = data["Date"].dt.strftime("%Y-%m-%d").tolist()
        prices = close_series.astype(float).tolist()

        return jsonify({
            "dates": dates,
            "prices": prices
        })

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/user_history")
def user_history():

    print("SESSION:", session)

    if "username" not in session:
        print("NO USER IN SESSION")
        return jsonify([])

    rows = Search.query.filter_by(
    username=session["username"]
    ).order_by(Search.id.desc()).limit(5).all()
    print("DB ROWS:", rows)

    history = []
    for r in rows:
        history.append({
            "stock": r[0],
            "price": r[1],
            "time": r[2]
        })

    return jsonify(history)

# ---------------- FEEDBACK ----------------
@app.route("/feedback", methods=["POST"])
def feedback():
    if "username" not in session:
        return jsonify({"success": False})

    message = request.form.get("message")
    username = session["username"]

    # Save to text file
    with open("user_feedback.txt", "a", encoding="utf-8") as f:
        f.write(f"{datetime.now()} | {username} | {message}\n")

    return jsonify({"success": True})

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
