import os
import io
from typing import Optional
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaFileUpload

# Scope allows creating files in the user's Drive and accessing files created by the app
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'  # client secrets from Google Cloud Console
TOKEN_FILE = 'token.json'


def get_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"{CREDENTIALS_FILE} not found. Create OAuth credentials in Google Cloud Console and save as {CREDENTIALS_FILE} in the backend folder."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(TOKEN_FILE, 'w') as token:
                token.write(creds.to_json())
    return creds


def upload_text_file(filename: str, content: str, folder_id: Optional[str] = None):
    """Uploads a plain text file to Google Drive and returns the file metadata dict."""
    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds)

    file_metadata = {'name': filename}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    fh = io.BytesIO(content.encode('utf-8'))
    media = MediaIoBaseUpload(fh, mimetype='text/plain')

    file = service.files().create(body=file_metadata, media_body=media, fields='id, name, webViewLink').execute()
    return file


def upload_media_file(path: str, filename: str, mimetype: str, folder_id: Optional[str] = None):
    """Upload a binary file on disk to Drive and return metadata."""
    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds)

    file_metadata = {'name': filename}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(path, mimetype=mimetype, resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields='id, name, webViewLink').execute()
    return file
