from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
import tempfile
import os
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Meeting Recorder Backend (scaffold)")


# Allow the Vite dev server (and localhost) to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from pydantic import BaseModel
# Import Drive helper lazily inside the handler to avoid import-time errors
# (e.g., missing Google dependencies or credentials) when the server starts.


class SaveTranscriptRequest(BaseModel):
    filename: str
    content: str
    folder_id: Optional[str] = None


@app.post('/save-transcript')
async def save_transcript(req: SaveTranscriptRequest):
    """Upload a transcript to the authenticated user's Google Drive.

    First-time use will trigger an OAuth consent flow in the server's environment
    (it will open a browser to complete authorization and save `token.json`).
    """
    try:
        # Lazy import so server startup doesn't fail if Drive deps/credentials are missing
        from drive import upload_text_file

        file = upload_text_file(req.filename, req.content, req.folder_id)
        return {"status": "uploaded", "file": file}
    except FileNotFoundError as fnf:
        return JSONResponse(status_code=400, content={"error": str(fnf)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})



class SummarizeRequest(BaseModel):
    text: str
    num_sentences: Optional[int] = 3


@app.post('/summarize')
async def summarize(req: SummarizeRequest):
    """Return an extractive summary and simple action-item extraction for the provided text."""
    try:
        # Lazy imports for optional summarization dependencies
        from sumy.parsers.plaintext import PlaintextParser
        from sumy.nlp.tokenizers import Tokenizer
        from sumy.summarizers.text_rank import TextRankSummarizer
        import nltk

        # ensure NLTK tokenizers are available for sentence tokenization
        try:
            nltk.data.find('tokenizers/punkt')
        except Exception:
            nltk.download('punkt')
        # Some environments (and versions of sumy) may look for 'punkt_tab'. Try to ensure it too.
        try:
            nltk.data.find('tokenizers/punkt_tab')
        except Exception:
            try:
                nltk.download('punkt_tab')
            except Exception:
                # If punkt_tab isn't available via downloader, ignore and proceed; tokenizer may still work.
                pass

        text = req.text or ""
        num_sentences = req.num_sentences or 3

        parser = PlaintextParser.from_string(text, Tokenizer('english'))
        summarizer = TextRankSummarizer()
        summary_sentences = summarizer(parser.document, num_sentences)
        summary = ' '.join(str(s) for s in summary_sentences)

        # Simple action-item extraction using keyword matching over sentences
        from nltk.tokenize import sent_tokenize

        sentences = sent_tokenize(text)
        keywords = [
            'action', 'todo', 'follow up', 'follow-up', 'deadline', 'due', 'should', 'must',
            'need to', 'assign', 'please', 'will', "let's", 'ask', 'schedule', 'follow'
        ]
        action_items = [s for s in sentences if any(k in s.lower() for k in keywords)]
        # Deduplicate while preserving order
        seen = set()
        deduped = []
        for s in action_items:
            if s not in seen:
                seen.add(s)
                deduped.append(s)

        return {"summary": summary, "action_items": deduped}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# Optional import of whisper. If not installed, endpoints will return a helpful message.
try:
    import whisper
except Exception:
    whisper = None


# Cache the loaded whisper model to avoid re-loading on each request
_whisper_model: Optional[object] = None


def get_whisper_model():
    global _whisper_model
    if whisper is None:
        raise RuntimeError("Whisper package is not installed. See backend/README.md to install dependencies.")
    if _whisper_model is None:
        # Load the lightweight 'base' model by default
        _whisper_model = whisper.load_model("base")
    return _whisper_model


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/start-recording")
async def start_recording(meeting_id: str):
    # Placeholder: in a real system, this would trigger a recorder service
    return {"meeting_id": meeting_id, "status": "recording_started"}


@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)):
    # Save uploaded audio file temporarily; attempt transcription with local Whisper if available
    try:
        suffix = os.path.splitext(file.filename)[1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        transcription_text = "(transcription unavailable - whisper not installed)"
        speakers = []
        action_items = []

        try:
            model = get_whisper_model()
            # Run transcription (this may take some time depending on model/hardware)
            result = model.transcribe(tmp_path)
            transcription_text = result.get("text", "")
        except RuntimeError as re:
            # Whisper not installed — return helpful instruction
            transcription_text = str(re)
        except FileNotFoundError as fnf:
            # Common on Windows when ffmpeg is missing (Whisper calls ffmpeg)
            transcription_text = (
                "(transcription error: ffmpeg not found on the system PATH. "
                "Install ffmpeg and add it to PATH — see backend/README.md for instructions. "
                f"Original error: {fnf}")
        except Exception as e:
            transcription_text = f"(transcription error: {e})"

        # Return response and ensure temporary file is cleaned up
        response = {
            "filename": file.filename,
            "saved_path": tmp_path,
            "transcription": transcription_text,
            "speakers": speakers,
            "action_items": action_items,
        }
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            # ignore cleanup errors
            pass

        return response
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/summary")
async def summary(meeting_id: str):
    # Placeholder summary endpoint
    return {"meeting_id": meeting_id, "summary": "(summary placeholder)"}


@app.post('/save-audio')
async def save_audio_to_drive(file: UploadFile = File(...), folder_id: Optional[str] = None):
    """Accept an audio upload and save it to Google Drive."""
    try:
        suffix = os.path.splitext(file.filename)[1] or ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        try:
            # Lazy import Drive media helper
            from drive import upload_media_file

            mimetype = file.content_type or 'audio/webm'
            uploaded = upload_media_file(tmp_path, file.filename, mimetype, folder_id)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

        return {"status": "uploaded", "file": uploaded}
    except FileNotFoundError as fnf:
        return JSONResponse(status_code=400, content={"error": str(fnf)})
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
