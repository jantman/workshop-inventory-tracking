import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from flask import current_app

# Google Sheets API scope
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

class GoogleAuth:
    """Handles Google OAuth 2.0 authentication for Google Sheets API"""
    
    def __init__(self, credentials_file=None, token_file=None):
        self.credentials_file = credentials_file or current_app.config.get('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
        self.token_file = token_file or current_app.config.get('GOOGLE_TOKEN_FILE', 'token.json')
        self._creds = None
        self._service = None
    
    def authenticate(self):
        """Authenticate with Google and return credentials"""
        creds = None
        
        # Load existing token if available
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        
        # If there are no (valid) credentials available, let the user log in
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                current_app.logger.info('Refreshing expired Google credentials')
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Google credentials file not found: {self.credentials_file}\n"
                        "Please download the credentials.json file from Google Cloud Console "
                        "and place it in the project root."
                    )
                
                current_app.logger.info('Starting OAuth 2.0 flow for new credentials')
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            
            # Save the credentials for the next run
            with open(self.token_file, 'w') as token:
                token.write(creds.to_json())
                current_app.logger.info(f'Saved new credentials to {self.token_file}')
        
        self._creds = creds
        return creds
    
    def get_service(self):
        """Get authenticated Google Sheets service"""
        if not self._service:
            if not self._creds:
                self.authenticate()
            self._service = build('sheets', 'v4', credentials=self._creds)
            current_app.logger.info('Google Sheets service initialized')
        return self._service
    
    @property
    def credentials(self):
        """Get current credentials"""
        if not self._creds:
            self.authenticate()
        return self._creds
    
    def is_authenticated(self):
        """Check if we have valid credentials"""
        try:
            creds = self.credentials
            return creds and creds.valid
        except Exception as e:
            current_app.logger.error(f'Authentication check failed: {e}')
            return False