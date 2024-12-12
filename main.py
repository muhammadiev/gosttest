from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional, Dict
from docx import Document
import random
import requests

app = FastAPI()

# Serve static files (e.g., CSS/JS)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Telegram Bot Token (replace with your actual token)
TELEGRAM_BOT_TOKEN = "7063427428:AAHIiKGXCuMjwgEhz5LeRYQtUXFN7bU4Lws"

# Simulating session storage
session_data: Dict[str, dict] = {}

# Global variable to store correct answers
t_answer = {}


# Function to parse questions and answers from a .docx file
def parse_questions_from_docx(docx_file_path: str, num_questions: int = 30):
    try:
        document = Document(docx_file_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading document: {e}")

    all_questions = []
    answers = {}

    for table in document.tables:
        for row in table.rows[1:]:  # Skip the header row
            cells = row.cells
            if len(cells) >= 5:
                question_id = f"q{len(all_questions) + 1}"
                question_text = cells[1].text.strip()
                correct_answer = cells[2].text.strip()
                options = [
                    cells[2].text.strip(),
                    cells[3].text.strip(),
                    cells[4].text.strip(),
                ]
                random.shuffle(options)

                all_questions.append({
                    "id": question_id,
                    "question": question_text,
                    "options": options,
                })
                answers[question_id] = correct_answer

    if len(all_questions) < num_questions:
        return all_questions, answers

    selected_questions = random.sample(all_questions, num_questions)
    return selected_questions, answers


@app.get("/", response_class=FileResponse)
async def serve_main_page(telegram_id: Optional[str] = Query(None)):
    """
    Serve the main HTML page and store telegram_id in session_data.
    """
    if telegram_id:
        print(f"Received Telegram ID: {telegram_id}")
        # Store the Telegram ID in the session with a status
        session_data[telegram_id] = {"status": "active"}
    return FileResponse("templates/index.html")


@app.get("/get-questions")
async def get_questions():
    """
    Fetch and return quiz questions.
    """
    global t_answer
    try:
        questions, t_answer = parse_questions_from_docx("quiz.docx", num_questions=30)
        if not questions:
            raise HTTPException(status_code=400, detail="No questions found in the document.")
        return JSONResponse(content={"questions": questions})
    except HTTPException as e:
        return JSONResponse(content={"error": e.detail}, status_code=e.status_code)


def send_score_to_telegram(telegram_id: str, score: int, total: int):
    """
    Send the user's score to Telegram via the bot.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    message = f"Your quiz is complete! 🎉\nYou scored: {score} / 30."

    payload = {
        "chat_id": telegram_id,
        "text": message,
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"Score sent to Telegram user {telegram_id}.")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send score to Telegram user {telegram_id}: {e}")


@app.post("/submit-answers")
async def submit_answers(request: Request):
    """
    Process submitted answers and calculate the score.
    """
    global t_answer
    try:
        user_answers = await request.json()
        print(f"Received request: {user_answers}")

        # Ensure Telegram ID is included in the submission
        telegram_id = user_answers.pop("telegram_id", None)
        if not telegram_id:
            raise HTTPException(status_code=400, detail="Telegram ID is required.")

        # Ensure the Telegram ID exists in session data
        if telegram_id not in session_data or session_data[telegram_id].get("status") != "active":
            raise HTTPException(status_code=400, detail="Invalid or inactive Telegram session.")

        if not t_answer:
            raise HTTPException(status_code=400,
                                detail="Questions and answers not loaded. Please fetch questions first.")

        # Calculate the user's score
        score = sum(1 for question_id, user_answer in user_answers.items()
                    if t_answer.get(question_id) == user_answer)

        # Send the score to the Telegram user
        send_score_to_telegram(telegram_id, score, len(t_answer))

        return JSONResponse(content={"score": score, "total": 30})
    except Exception as e:
        print(f"Error processing request: {e}")
        raise HTTPException(status_code=400, detail="Invalid request format.")
