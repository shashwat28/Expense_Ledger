import os
import csv
import re
import time
from datetime import datetime, timedelta
import base64
from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scope definitions for accessing Gmail safely
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def get_gmail_service():
    """Handles secure OAuth2 authentication with Gmail API."""
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                raise FileNotFoundError("Missing 'credentials.json' file in project folder!")
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

def parse_gpay_email(html_body, subject, email_timestamp):
    """
    Tailored parsing engine optimized for HDFC Bank UPI notification formats.
    Extracts transaction attributes, tracking fields, and target recipients.
    """
    soup = BeautifulSoup(html_body, 'html.parser')
    text = re.sub(r'\s+', ' ', soup.get_text(separator=' ').strip())
    
    # 1. Extract Amount (e.g., Rs.25.00)
    amount_match = re.search(r'(?:Rs\.|₹)\s*([\d,]+\.\d{2})', text, re.IGNORECASE)
    amount = amount_match.group(1).replace(',', '') if amount_match else "0.00"
    
    # 2. Extract Account Ending digits (e.g., 3074)
    account_match = re.search(r'account ending (\d+)', text, re.IGNORECASE)
    source_account = f"HDFC account ending {account_match.group(1)}" if account_match else "HDFC Account"
    
    # 3. Extract Recipient / Merchant Name from parentheses (e.g., SHEZAN CAKE HOUSE AND SNACKS)
    recipient_match = re.search(r'\(([^)]+)\)', text)
    recipient = recipient_match.group(1).strip() if recipient_match else "Unknown Recipient"
    
    # 4. Extract VPA Address string (e.g., q506057232@ybl)
    vpa_match = re.search(r'towards VPA\s+([A-Za-z0-9@._-]+)', text, re.IGNORECASE)
    vpa_address = vpa_match.group(1).strip() if vpa_match else "N/A"
    
    # 5. Extract Transaction Reference Number (e.g., 130341264322)
    tx_id_match = re.search(r'(?:reference no\.|Transaction ID|Txn ID)[:\s]+(\d+)', text, re.IGNORECASE)
    tx_id = tx_id_match.group(1).strip() if tx_id_match else "N/A"
    
    # 6. Process the Combined Date and Time Timestamp
    date_match = re.search(r'on\s+(\d{2}-\d{2}-\d{2,4})', text, re.IGNORECASE)
    if date_match:
        extracted_date = date_match.group(1).strip()
        try:
            time_part = email_timestamp.split(" ")[1]  # Extracts HH:MM:SS
            final_timestamp = f"{extracted_date} {time_part}"
        except IndexError:
            final_timestamp = email_timestamp
    else:
        final_timestamp = email_timestamp

    # 7. Determine status characteristics mapping (DEBIT vs CREDIT)
    txn_type = "DEBIT"
    if "credited" in text.lower() or "received" in text.lower():
        txn_type = "CREDIT"
        
    return {
        "Transaction_Timestamp": final_timestamp,
        "Amount": amount,
        "Recipient_Name": recipient,
        "VPA_Address": vpa_address,
        "Transaction_ID": tx_id,
        "Source_Account": source_account,
        "Type": txn_type,
        "Email_Subject": subject
    }

def fetch_transactions_pipeline(start_date):
    """Queries Gmail API for transaction alerts starting from a dynamic start_date."""
    try:
        service = get_gmail_service()
        
        # Format date for Gmail queries (YYYY/MM/DD)
        after_query = start_date.strftime('%Y/%m/%d')
        query = f'after:{after_query} ("HDFC Bank" OR "Google Pay") ("debited" OR "towards VPA" OR "transaction reference")'
        
        print(f"🔍 Searching emails from {start_date.strftime('%Y-%m-%d')} onward...")
        print(f"📡 Query string: {query}")
        
        response = service.users().messages().list(userId='me', q=query).execute()
        messages = response.get('messages', [])
        
        # Paginate through large volumes of history cleanly
        while 'nextPageToken' in response:
            page_token = response['nextPageToken']
            response = service.users().messages().list(userId='me', q=query, pageToken=page_token).execute()
            messages.extend(response.get('messages', []))
            
        if not messages:
            print("❌ No matching transaction emails found within this timeframe.")
            return

        print(f"📦 Found {len(messages)} transaction logs. Extracting fields safely...")
        parsed_data_list = []
        
        for index, msg in enumerate(messages, start=1):
            msg_id = msg['id']
            
            # Adaptive delay to prevent hitting peak per-minute quotas
            time.sleep(0.3)
            
            # Fetch message payload with an automatic retry block for rate limits
            message = None
            for retry in range(3):
                try:
                    message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
                    break
                except HttpError as error:
                    if error.resp.status == 403:
                        wait_time = 15 * (retry + 1)
                        print(f"\n⚠️ Rate limit hit. Cooling down for {wait_time} seconds (Retry {retry+1}/3)...")
                        time.sleep(wait_time)
                    else:
                        raise error

            if not message:
                print(f"⏭️ Skipping email ID {msg_id} due to persistent API errors.")
                continue
            
            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), "No Subject")
            
            internal_date_ms = int(message.get('internalDate', 0))
            email_date_formatted = datetime.fromtimestamp(internal_date_ms / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
            
            # Clean body fallback sequence
            html_body = ""
            if 'parts' in payload:
                for part in payload['parts']:
                    if part.get('mimeType') in ['text/html', 'text/plain']:
                        body_data = part.get('body', {}).get('data', '')
                        html_body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')
                        break
            else:
                body_data = payload.get('body', {}).get('data', '')
                if body_data:
                    html_body = base64.urlsafe_b64decode(body_data).decode('utf-8', errors='ignore')

            if not html_body:
                continue
                
            transaction_record = parse_gpay_email(html_body, subject, email_date_formatted)
            parsed_data_list.append(transaction_record)
            
            # Visual progression updates
            if index % 10 == 0 or index == len(messages):
                print(f"⏳ Extracted {index}/{len(messages)} rows...")

        # Export structured matrix to CSV
        csv_filename = "gpay_transactions.csv"
        csv_columns = ["Transaction_Timestamp", "Amount", "Recipient_Name", "VPA_Address", "Transaction_ID", "Source_Account", "Type", "Email_Subject"]
        
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=csv_columns)
            writer.writeheader()
            for record in parsed_data_list:
                writer.writerow(record)
                
        print(f"\n✅ Pipeline complete! {len(parsed_data_list)} items written to: {os.path.abspath(csv_filename)}")
        
    except Exception as e:
        print(f"❌ Critical Pipeline Failure: {e}")

if __name__ == '__main__':
    # =========================================================================
    # ⏱️ TIMEFRAME CONTROL CENTER
    # Modify the calculation below to change the duration of your data fetch.
    # =========================================================================
    # target_start_date = datetime.now() - timedelta(hours=24)
    # target_start_date = datetime.now() - timedelta(days=7)
    # target_start_date = datetime.now() - timedelta(days=90)
    # target_start_date = datetime(2026, 1, 1)


    # CURRENT SETTING: Last 365 Days (1 Full Year)
    target_start_date = datetime.now() - timedelta(days=365)
    
    # Execute the data pipeline
    fetch_transactions_pipeline(target_start_date)
