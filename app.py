import os
import psycopg2
from flask import Flask, request, jsonify
import g4f

DATABASE_URL = os.getenv("DATABASE_URL")
MAX_HISTORY_LENGTH = 20
DEFAULT_MODEL = "gpt-4"

app = Flask(__name__)

def get_db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    chat_id BIGINT,
                    role TEXT,
                    content TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

def get_history(chat_id):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT role, content FROM history
                WHERE chat_id = %s
                ORDER BY timestamp ASC
                LIMIT %s
            """, (chat_id, MAX_HISTORY_LENGTH))
            rows = cur.fetchall()
    return [{"role": row[0], "content": row[1]} for row in rows]

def append_history(chat_id, role, content):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO history (chat_id, role, content)
                VALUES (%s, %s, %s)
            """, (chat_id, role, content))
            conn.commit()

def reset_history(chat_id):
    with get_db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM history WHERE chat_id = %s", (chat_id,))
            conn.commit()

init_db()

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "https://muvvy.github.io"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

@app.route("/api/ai", methods=["POST", "OPTIONS"])
def api_ai():
    if request.method == "OPTIONS":
        return '', 200

    data = request.get_json(force=True)
    chat_id = data.get("chat_id")
    message = data.get("message", "")

    if not chat_id or not message:
        return jsonify({"response": "chat_id и message обязательны"}), 400

    append_history(chat_id, "user", message)

    try:
        response = g4f.ChatCompletion.create(
            model=DEFAULT_MODEL,
            messages=get_history(chat_id)
        )
    except Exception as e:
        print(f"Ошибка g4f: {e}")
        response = "Ошибка при обработке запроса."

    append_history(chat_id, "assistant", response)
    return jsonify({"response": response})

@app.route("/api/clear_history", methods=["POST"])
def clear_history():
    data = request.get_json(force=True)
    chat_id = data.get("chat_id")
    if not chat_id:
        return jsonify({"error": "chat_id обязателен"}), 400
    reset_history(chat_id)
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host="0.0.0.0", port=port)
