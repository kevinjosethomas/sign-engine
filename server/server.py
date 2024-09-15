import os
import re
import json
from openai import OpenAI

import dotenv
import psycopg2
from flask_cors import CORS
from flask import Flask, Response, request
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer


dotenv.load_dotenv()
app = Flask(__name__)
CORS(app)
db = psycopg2.connect(
    database="poses",
    host="localhost",
    user="postgres",
    password=os.getenv("POSTGRES_PASSWORD"),
    port=5432,
)
register_vector(db)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


fingerspelling = {}
for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    file_path = os.path.join("data/alphabets", f"{letter}.json")
    with open(file_path, "r") as file:
        fingerspelling[letter] = json.load(file)


@app.route("/pose", methods=["POST"])
def pose():
    data = request.get_json()
    words = data.get("words", "").lower().strip()
    animations = []

    if not words:
        return Response(status=400)

    if words != "hello":
        response = client.chat.completions.create(
            model="ft:gpt-4o-mini-2024-07-18:personal:text2gloss-full-data:A7WORNDv",
            messages=[
                {
                    "role": "system",
                    "content": "Translate English to ASL Gloss Grammar",
                },
                {
                    "role": "user",
                    "content": words,
                },
            ],
        )

        words = response.choices[0].message.content
        words = re.sub(r"DESC-|X-|-LRB-|-RRB-", "", words)

    words = words.split()

    cur = db.cursor()
    for word in words:
        embedding = embedding_model.encode(word)
        cur.execute(
            "SELECT word, poses, (embedding <=> %s) AS cosine_similarity FROM signs ORDER BY cosine_similarity ASC LIMIT 1",
            (embedding,),
        )
        result = cur.fetchone()

        if (1 - result[2]) < 0.70:
            animation = []
            for letter in word.upper():
                animation += fingerspelling.get(letter, [])

            for i in range(len(animation)):
                animation[i]["word"] = f"fs-{word.upper()}"

            animations += animation
        else:
            for i in range(len(result[1])):
                result[1][i]["word"] = result[0]

            animations += result[1]

    return Response(json.dumps(animations), status=200)


if __name__ == "__main__":
    app.run()
