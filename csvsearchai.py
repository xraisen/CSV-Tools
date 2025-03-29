from flask import Flask, render_template_string, request, session, redirect, url_for, jsonify, has_request_context
import pandas as pd
import google.generativeai as genai
import threading
import webbrowser
import os
import io
import json
import re
from flask import send_file
from datetime import datetime
import shutil

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secure_secret_key'  # Replace with a secure key
app.config['DEBUG'] = True
app.config['PROPAGATE_EXCEPTIONS'] = True

# Global variables
DEFAULT_CSV_PATH = r""  # Set a default CSV path if needed
UPLOAD_FOLDER = 'uploads'  # Directory to store uploaded CSV files
SETTINGS_FILE = 'settings.json'  # File to store persistent settings
CHAT_HISTORY_FILE = 'chat_history.json'  # File to store chat history
CHUNK_SIZE = 10000  # For chunk-based searching (unused now)
DEFAULT_ROWS_PER_PAGE = 10  # Default for pagination
# Removed DEFAULT_SEARCH_COLUMN as search is now across all columns

# Global cache to optimize file I/O and parsing
csv_cache = {}

# Create uploads directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Caching mechanism for CSV file ---
def load_csv_cached(csv_path):
    """
    Loads the CSV file fully into memory using a caching mechanism.
    It checks the file's modification time and caches the DataFrame.
    """
    try:
        mtime = os.path.getmtime(csv_path)
    except Exception as e:
        print(f"Error getting file modification time: {e}")
        return pd.DataFrame()
    key = (csv_path, mtime)
    if key in csv_cache:
        return csv_cache[key]
    else:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        # Clear previous cache entries (assuming one file at a time)
        csv_cache.clear()
        csv_cache[key] = df
        return df

# --- Settings and Chat History Helpers ---
def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading settings: {e}")
    # Removed search_column from persistent settings
    return {
        'csv_path': DEFAULT_CSV_PATH,
        'model': 'gemini-2.0-flash-thinking-exp-01-21',
        'dark_mode': False,
        'rows_per_page': DEFAULT_ROWS_PER_PAGE
    }

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Error saving settings: {e}")

def load_chat_history():
    try:
        if os.path.exists(CHAT_HISTORY_FILE):
            with open(CHAT_HISTORY_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error loading chat history: {e}")
    return []

def save_chat_history(chat_history):
    try:
        with open(CHAT_HISTORY_FILE, 'w') as f:
            json.dump(chat_history, f, indent=4)
    except Exception as e:
        print(f"Error saving chat history: {e}")

persistent_settings = load_settings()
persistent_chat_history = load_chat_history()

@app.teardown_appcontext
def clear_api_key(exception):
    if has_request_context():
        if 'api_key' in session:
            session.pop('api_key', None)
        # Clean up any combined columns when session ends
        if 'combined_columns' in session:
            session.pop('combined_columns', None)
        # Clear all custom columns when session ends
        if 'custom_columns' in session:
            session.pop('custom_columns', None)

# --- Restore Original Data Function ---
@app.route('/restore', methods=['POST'])
def restore_original():
    csv_path = session.get('csv_path', DEFAULT_CSV_PATH)
    if not csv_path:
        return jsonify({'error': 'No CSV file selected'}), 400
    if not os.path.exists(csv_path):
        return jsonify({'error': f'CSV file not found at path: {csv_path}'}), 400
    
    # Clear any combined columns from session
    if 'combined_columns' in session:
        session.pop('combined_columns', None)
    
    # Reload original data
    df = load_csv_cached(csv_path)
    if df.empty:
        return jsonify({'error': 'No data to restore'}), 400
    
    # Convert to our search results format
    search_results = []
    for idx, row in df.iterrows():
        search_results.append({
            'row_index': idx,
            'data': row.to_dict(),
            'matching_columns': []
        })
    
    # Update session with original data
    session['current_results'] = search_results
    
    return jsonify({
        'status': 'success',
        'message': 'Original data restored',
        'data': search_results
    })

# --- Optimized CSV Search Function Using Caching and Vectorized Operations ---
def chunk_search_csv(csv_path, search_text):
    """
    Instead of reading in chunks row by row, load the entire CSV using cache
    and use vectorized string operations to improve performance.
    Returns a list of dictionaries with row_index, data (row as dict),
    and matching_columns (list of columns where search_text was found).
    """
    df = load_csv_cached(csv_path)
    if df.empty:
        return []
    # Create a boolean DataFrame where each cell indicates if the cell contains search_text.
    mask = df.apply(lambda col: col.str.contains(search_text, case=False, na=False))
    any_match = mask.any(axis=1)
    matched_indices = df.index[any_match]
    
    results = []
    for idx in matched_indices:
        row = df.loc[idx]
        # Determine which columns matched using the precomputed mask.
        matching_columns = mask.loc[idx][mask.loc[idx]].index.tolist()
        results.append({
            'row_index': int(idx),
            'data': row.to_dict(),
            'matching_columns': matching_columns
        })
    return results

# --- Updated AI Response Function ---
def get_ai_response(search_summary, user_query, last_query):
    """Enhanced AI response with better error handling and action parsing."""
    # Validate inputs first
    if not isinstance(search_summary, dict) or not all(k in search_summary for k in ['columns', 'num_rows', 'sample_rows']):
        return {
            "response": "<div class='ai-error'><div class='ai-header'>Error</div><div class='ai-content'>Invalid search summary format</div></div>",
            "action": None,
            "chat_html": ""
        }
    
    api_key = session.get('api_key')
    model = session.get('model', 'gemini-2.0-flash-thinking-exp-01-21')
    if not api_key:
        return {
            "response": "<div class='ai-error'><div class='ai-header'>Error</div><div class='ai-content'>API key not set. Please configure it in Settings.</div></div>",
            "action": None,
            "chat_html": ""
        }
    
    if search_summary['num_rows'] == 0:
        return {
            "response": "<div class='ai-info'><div class='ai-header'>Information</div><div class='ai-content'>No search results to analyze.</div></div>",
            "action": None,
            "chat_html": ""
        }

    columns = search_summary['columns']
    num_rows = search_summary['num_rows']
    sample_rows = search_summary['sample_rows']
    
    sample_text = ""
    for i, row in enumerate(sample_rows):
        row_info = f"Row {i+1} (Index {row.get('row_index', 'N/A')}): "
        row_info += ", ".join([f"{k}={v}" for k, v in row.items() if k != 'row_index'])
        sample_text += row_info + "\n"

    ai_role = (
        f"You are an AI assistant specialized in CSV data analysis. "
        f"Based on the search results (searched across all columns with query '{last_query}'), you can:\n"
        "- Provide information about the search results without modifying the table (e.g., total row count, counts of specific data).\n"
        "- Manipulate the table (e.g., sort, filter, combine columns).\n"
        "**Instructions:**\n"
        "- For queries requiring only information (e.g., 'How many are there on search results containing {last_query}?' or 'How many emails are there?'), respond with the answer in HTML format without a <script> tag.\n"
        "- For queries requiring table manipulation (e.g., sorting, combining columns), include a JSON-like instruction in a <script type='ai-action'> tag.\n"
        "**Examples:**\n"
        "1. Query: 'How many are there on search results containing {last_query}?' Response: "
        "<div class='ai-header'>Row Count</div><div class='ai-content'>There are {num_rows} rows in the search results.</div>\n"
        "2. Query: 'How many emails are there?' Response: "
        "<div class='ai-header'>Email Count</div><div class='ai-content'>There are X emails in the search results.</div>\n"
        "3. Query: 'How many phone numbers are there?' Response: "
        "<div class='ai-header'>Phone Count</div><div class='ai-content'>There are X phone numbers in columns: {', '.join([c for c in columns if 'phone' in c.lower()])}.</div>\n"
        "3. Query: 'Combine all emails containing {last_query} and name the column header \"EMAIL SHEETS\"' Response: "
        "<div class='ai-header'>Combining Emails</div><div class='ai-content'>A new column \"EMAIL SHEETS\" has been added with emails containing \"{last_query}\".</div>"
        "<script type='ai-action'>{{\"action\": \"combine\", \"column\": \"email\", \"condition\": \"contains {last_query}\", \"new_column\": \"EMAIL SHEETS\"}}</script>\n"
        "4. Query: 'Remove all email headers, combine them, and put them into \"email ko\" column' Response: "
        "<div class='ai-header'>Merging Emails</div><div class='ai-content'>Combined all email columns into \"email ko\".</div>"
        "<script type='ai-action'>{{\"action\": \"merge\", \"columns\": [\"Email1\", \"Email2\", \"Email3\", \"Email4\", \"Email5\"], \"new_column\": \"email ko\"}}</script>\n"
        "5. Query: 'How many ahmed that name starts with letter J' Response: Check for 'name' column; if absent, suggest alternatives.\n"
        "**Condition Format for Actions:** Use 'column contains value' or 'column is not empty'.\n"
        "Ensure column names match those in the table: {', '.join(columns)}.\n"
        "Respond in HTML with <div class='ai-header'> and <div class='ai-content'> tags."
    )
    summary = (
        f"Search results:\n- Columns: {', '.join(columns)}\n- Rows: {num_rows}\n"
        f"Sample:\n{sample_text}"
    )
    input_text = f"{ai_role}\n\n{summary}\n\nUser query: {user_query}"

    try:
        genai.configure(api_key=api_key)
        model_instance = genai.GenerativeModel(model)
        response = model_instance.generate_content(input_text)
        response_text = response.text
        
        # Enhanced response cleaning and formatting
        response_text = re.sub(r'^```html\s*\n', '', response_text, flags=re.MULTILINE)
        response_text = re.sub(r'\n```$', '', response_text, flags=re.MULTILINE)
        
        # Standardize action script formatting
        script_start = response_text.find("<script type='ai-action'>")
        script_end = response_text.find("</script>", script_start) + 9 if script_start != -1 else -1
        
        if script_start != -1 and script_end != -1:
            # Extract and validate action script
            script_content = response_text[script_start:script_end]
            try:
                action = json.loads(script_content[script_content.find('>')+1:script_content.rfind('<')].strip())
                if not isinstance(action, dict) or 'action' not in action:
                    script_content = ""
            except json.JSONDecodeError:
                script_content = ""
                
            # Format response with consistent spacing
            before_script = response_text[:script_start].strip()
            after_script = response_text[script_end:].strip()
            
            response_text = f"{before_script}\n\n{script_content}\n\n{after_script}"
        
        # Standardize line breaks and spacing
        response_text = response_text.replace('\n\n', '<br><br>')
        response_text = response_text.replace('\n', '<br>')

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_response = (
            "<div class='ai-message'>"
            f"<div class='ai-timestamp'>{timestamp}</div>"
            f"{response_text}"
            "</div>"
        )
        chat_history = session.get('chat_history', persistent_chat_history)
        chat_entry = {
            "id": len(chat_history) + 1,
            "query": user_query,
            "response": response.text,
            "timestamp": timestamp
        }
        chat_history.append(chat_entry)
        session['chat_history'] = chat_history
        save_chat_history(chat_history)

        chat_html = ''
        for entry in chat_history:
            chat_html += (
                f'<details class="chat-entry" data-id="{entry["id"]}" data-query="{entry["query"].lower()}">'
                f'<summary><span>{entry["query"]}</span><button class="delete-chat" onclick="deleteChatEntry({entry["id"]})">Delete</button></summary>'
                f'<div class="chat-timestamp">{entry["timestamp"]}</div>'
                f'<p>{entry["response"]}</p>'
                '</details>'
            )

        return {
            "response": formatted_response,
            "action": None,
            "chat_html": chat_html
        }
    except Exception as e:
        error_response = (
            "<div class='ai-error'><div class='ai-header'>Error</div>"
            "<div class='ai-content'>An error occurred: " + str(e) + "</div></div>"
        )
        return {
            "response": error_response,
            "action": None,
            "chat_html": ""
        }

# --- Updated Manipulate Results Function ---
def manipulate_results(search_results, action):
    if not search_results:
        return search_results
    try:
        if action['action'] == 'sort':
            column = action.get('column')
            order = action.get('order', 'ascending')
            if column in search_results[0]['data']:
                search_results.sort(
                    key=lambda x: x['data'][column].lower() if isinstance(x['data'][column], str) else x['data'][column],
                    reverse=(order.lower() == 'descending')
                )
        elif action['action'] == 'filter':
            conditions = action.get('conditions', [])
            relation = action.get('relation', 'AND')
            if conditions:
                filtered_results = []
                for result in search_results:
                    match = True
                    for condition in conditions:
                        column = condition.get('column')
                        cond = condition.get('condition', '')
                        if column in result['data']:
                            if 'contains' in cond:
                                value = cond.split('contains')[1].strip().lower()
                                if value not in str(result['data'][column]).lower():
                                    match = False
                                    if relation == 'OR':
                                        match = True
                                        break
                            elif 'is not empty' in cond:
                                if not str(result['data'][column]).strip():
                                    match = False
                                    if relation == 'OR':
                                        match = True
                                        break
                    if match:
                        filtered_results.append(result)
                search_results = filtered_results
        elif action['action'] == 'select_columns':
            columns = [col.strip('\"').strip() for col in action.get('columns', [])]
            if columns:
                # Validate requested columns exist in data
                available_columns = list(search_results[0]['data'].keys()) if search_results else []
            missing_columns = [col for col in columns if col not in available_columns]
            
            if missing_columns:
                return [{
                    'row_index': 0,
                    'data': {"Error": f"Columns not found: {', '.join(missing_columns)}"},
                    'matching_columns': []
                }]
                
            # Always update session with selected columns
            session['columns'] = columns
            
            # Update search results with selected columns
            filtered_results = []
            for result in search_results:
                new_data = {col: result['data'][col] for col in columns if col in result['data']}
                if new_data:  # Only include results that have the requested columns
                    result['data'] = new_data
                    result['matching_columns'] = [col for col in result['matching_columns'] if col in columns]
                    filtered_results.append(result)
            
            search_results = filtered_results
            # Force reload of CSV in next search to ensure column selections persist
            csv_cache.clear()
        elif action['action'] == 'deduplicate':
            column = action.get('column')
            if column in search_results[0]['data']:
                seen = set()
                deduplicated = []
                for result in search_results:
                    value = result['data'][column]
                    if value not in seen:
                        seen.add(value)
                        deduplicated.append(result)
                search_results = deduplicated
        elif action['action'] == 'group':
            column = action.get('column')
            aggregate = action.get('aggregate', 'count')
            if column in search_results[0]['data']:
                grouped = {}
                for result in search_results:
                    key = result['data'][column]
                    grouped.setdefault(key, []).append(result)
                new_results = []
                for key, group in grouped.items():
                    if aggregate == 'count':
                        new_data = {column: key, 'count': len(group)}
                        new_results.append({
                            'row_index': group[0]['row_index'],
                            'data': new_data,
                            'matching_columns': []
                        })
                search_results = new_results
        elif action['action'] == 'count':
            condition = action.get('condition', '')
            parts = condition.split()
            if 'contains' in parts:
                contains_index = parts.index('contains')
                column = ' '.join(parts[:contains_index])
                value = ' '.join(parts[contains_index + 1:]).lower()
                if column in search_results[0]['data']:
                    count = sum(1 for result in search_results if value in str(result['data'].get(column, '')).lower())
                    search_results = [{
                        'row_index': 0,
                        'data': {'Result': f"Count of rows where {column} contains {value}", 'Count': count},
                        'matching_columns': []
                    }]
                else:
                    search_results = [{
                        'row_index': 0,
                        'data': {'Result': f"Column '{column}' not found", 'Count': 0},
                        'matching_columns': []
                    }]
            elif 'is not empty' in condition:
                column = condition.replace(' is not empty', '').strip()
                if column in search_results[0]['data']:
                    count = sum(1 for result in search_results if result['data'].get(column, '') != '')
                    search_results = [{
                        'row_index': 0,
                        'data': {'Result': f"Count of rows where {column} is not empty", 'Count': count},
                        'matching_columns': []
                    }]
                else:
                    search_results = [{
                        'row_index': 0,
                        'data': {'Result': f"Column '{column}' not found", 'Count': 0},
                        'matching_columns': []
                    }]
            else:
                search_results = [{
                    'row_index': 0,
                    'data': {'Result': "Invalid condition format", 'Count': 0},
                    'matching_columns': []
                }]
        elif action['action'] == 'combine':
            # Validate column names before combining
            column = action.get('column')
            condition = action.get('condition', '')
            new_column = action.get('new_column')
            
            if not column or not new_column:
                return [{
                    'row_index': 0,
                    'data': {'Error': 'Both column and new_column must be specified for combine action'},
                    'matching_columns': []
                }]
                
            if column not in search_results[0]['data']:
                return [{
                    'row_index': 0,
                    'data': {'Error': f"Column '{column}' not found in data"},
                    'matching_columns': []
                }]
                
            if 'contains' not in condition:
                return [{
                    'row_index': 0,
                    'data': {'Error': 'Combine action requires a "contains" condition'},
                    'matching_columns': []
                }]
                
            parts = condition.split()
            contains_index = parts.index('contains')
            value = ' '.join(parts[contains_index + 1:]).lower()
            
            # Store combined column in session for later cleanup
            if 'combined_columns' not in session:
                session['combined_columns'] = []
            session['combined_columns'].append(new_column)
            
            # Update the in-memory DataFrame cache
            csv_path = session.get('csv_path')
            if csv_path:
                df = load_csv_cached(csv_path)
                for idx, result in enumerate(search_results):
                    if value in str(result['data'][column]).lower():
                        df.at[result['row_index'], new_column] = result['data'][column]
                    else:
                        df.at[result['row_index'], new_column] = ""
                # Save the modified DataFrame back to CSV
                df.to_csv(csv_path, index=False)
                # Clear cache to force reload
                csv_cache.clear()
                # Update session with new columns
                if 'columns' in session:
                    session['columns'] = list(df.columns)
            
            for result in search_results:
                if value in str(result['data'][column]).lower():
                    result['data'][new_column] = result['data'][column]
                else:
                    result['data'][new_column] = ""
                
                if new_column not in result['matching_columns']:
                    result['matching_columns'].append(new_column)
        elif action['action'] == 'merge':
            columns_to_merge = action.get('columns', [])
            new_column = action.get('new_column')
            valid_columns = [col for col in columns_to_merge if col in search_results[0]['data']]
            if valid_columns:
                # Update the in-memory DataFrame cache
                csv_path = session.get('csv_path')
                if csv_path:
                    df = load_csv_cached(csv_path)
                    for idx, result in enumerate(search_results):
                        merged_value = ', '.join([str(result['data'].get(col, '')) for col in valid_columns if result['data'].get(col, '')])
                        df.at[result['row_index'], new_column] = merged_value
                    # Save the modified DataFrame back to CSV
                    df.to_csv(csv_path, index=False)
                    # Clear cache to force reload
                    csv_cache.clear()
                    # Update session with new columns
                    if 'columns' in session:
                        session['columns'] = list(df.columns)
                
                # Update search results
                for result in search_results:
                    merged_value = ', '.join([str(result['data'].get(col, '')) for col in valid_columns if result['data'].get(col, '')])
                    result['data'][new_column] = merged_value
        elif action['action'] == 'remove_no_match_columns':
            # Remove all columns that didn't match the search query
            removed_columns = set()
            for result in search_results:
                # Get all columns that didn't match
                no_match_cols = [col for col in result['data'] if col not in result['matching_columns']]
                # Track removed columns
                removed_columns.update(no_match_cols)
                # Remove them from the data
                for col in no_match_cols:
                    if col in result['data']:
                        del result['data'][col]
                # Also remove from matching_columns if present
                result['matching_columns'] = [col for col in result['matching_columns'] if col not in no_match_cols]
            
            # Generate clean response message
            if removed_columns:
                return [{
                    'row_index': 0,
                    'data': {
                        'Result': 'Removed columns not matching search',
                        'Columns': ', '.join(sorted(removed_columns))
                    },
                    'matching_columns': []
                }] + search_results
            else:
                return [{
                    'row_index': 0,
                    'data': {
                        'Result': 'No columns removed - all columns match search'
                    },
                    'matching_columns': []
                }] + search_results
        return search_results
    except Exception as e:
        print(f"Error in manipulate_results: {e}")
        return search_results

# --- Helper to Get CSV Columns ---
def get_csv_columns(csv_path):
    try:
        df = pd.read_csv(csv_path, nrows=1)
        return list(df.columns)
    except Exception as e:
        print(f"Error reading CSV columns: {e}")
        return []

# --- CSV Header Preview Endpoint ---
@app.route('/preview_csv_headers', methods=['POST'])
def preview_csv_headers():
    if 'csv_file' not in request.files:
        return jsonify({"error": "No file uploaded."})
    file = request.files['csv_file']
    if not file.filename.endswith('.csv'):
        return jsonify({"error": "Please upload a CSV file."})
    try:
        df = pd.read_csv(file, nrows=1)
        headers = list(df.columns)
        return jsonify({"headers": headers})
    except Exception as e:
        return jsonify({"error": f"Error reading CSV headers: {str(e)}"})

# --- Updated HTML Template ---
# Removed Search Column field; updated search form label.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>CSV Search + AI</title>
    <style>
        /* [Style definitions remain unchanged] */
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f7; color: #1d1d1f; margin: 0; padding: 20px; transition: background 0.3s, color 0.3s; }
        body.dark-mode { background: #1c2526; color: #e0e0e0; }
        body.dark-mode .highlight { background: #455a64; }
        .container { max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); position: relative; transition: background 0.3s; }
        body.dark-mode .container { background: #2c3e50; }
        h1 { font-size: 24px; margin-bottom: 20px; }
        h2 { font-size: 20px; margin-top: 20px; }
        .table-container { max-height: 400px; overflow-y: auto; margin-top: 20px; position: relative; }
        table { width: 100%; border-collapse: collapse; }
        th, td { border: 1px solid #e5e5e5; padding: 10px; text-align: left; }
        body.dark-mode th, body.dark-mode td { border-color: #4a5e72; }
        th { background: #f5f5f7; font-weight: bold; position: sticky; top: 0; z-index: 1; cursor: pointer; }
        body.dark-mode th { background: #3b4a5a; }
        .highlight { background: #ffeb3b; }
        .modal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1000; }
        .modal-content { background: white; margin: 10% auto; padding: 30px; width: 450px; border-radius: 8px; transition: background 0.3s; }
        body.dark-mode .modal-content { background: #2c3e50; }
        button, input[type="submit"] { padding: 8px 16px; background: #007aff; color: white; border: none; border-radius: 6px; cursor: pointer; transition: background 0.3s; }
        button:hover, input[type="submit"]:hover { background: #005bb5; }
        button:disabled, input[type="submit"]:disabled { background: #cccccc; cursor: not-allowed; }
        input[type="text"], select, input[type="file"], input[type="number"] { padding: 10px; width: 100%; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 15px; transition: border-color 0.3s; box-sizing: border-box; }
        body.dark-mode input[type="text"], body.dark-mode select, body.dark-mode input[type="file"], body.dark-mode input[type="number"] { background: #3b4a5a; color: #e0e0e0; border-color: #4a5e72; }
        #loadingOverlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 1001; }
        #loadingOverlay div { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); color: white; font-size: 20px; }
        footer { text-align: center; margin-top: 20px; }
        #aiResponse { margin-top: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 6px; background: #f9f9f9; max-height: 300px; overflow-y: auto; transition: background 0.3s, border-color 0.3s; }
        body.dark-mode #aiResponse { background: #3b4a5a; border-color: #4a5e72; }
        .ai-message { color: #333; margin-bottom: 15px; padding: 10px; border-left: 3px solid #007aff; }
        body.dark-mode .ai-message { color: #e0e0e0; border-left-color: #66b0ff; }
        .ai-error { color: #d32f2f; }
        .ai-info { color: #0288d1; }
        .ai-header { font-weight: bold; font-size: 16px; margin-bottom: 10px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
        body.dark-mode .ai-header { border-color: #4a5e72; }
        .ai-content { font-size: 14px; line-height: 1.5; }
        .ai-content pre { background: #f0f0f0; padding: 10px; border-radius: 4px; overflow-x: auto; }
        body.dark-mode .ai-content pre { background: #2a3b4c; }
        .ai-content ul { padding-left: 20px; }
        .ai-timestamp { font-size: 12px; color: #666; margin-bottom: 5px; }
        body.dark-mode .ai-timestamp { color: #b0b0b0; }
        .options { margin-top: 10px; font-size: 14px; display: flex; gap: 15px; align-items: center; }
        .options label { margin-right: 5px; }
        .options select { width: auto; display: inline-block; padding: 5px; }
        .pagination { margin-top: 10px; display: flex; gap: 10px; justify-content: center; }
        .pagination button { padding: 5px 10px; }
        .sidebar { position: fixed; top: 0; right: -300px; width: 300px; height: 100%; background: #f5f5f7; box-shadow: -2px 0 5px rgba(0,0,0,0.1); transition: right 0.3s; padding: 20px; overflow-y: auto; z-index: 999; }
        body.dark-mode .sidebar { background: #2c3e50; }
        .sidebar.open { right: 0; }
        .sidebar h3 { margin-top: 0; margin-bottom: 10px; }
        .chat-entry { margin-bottom: 15px; border-bottom: 1px solid #ddd; padding-bottom: 10px; transition: background 0.2s; }
        .chat-entry:hover { background: #f0f0f0; }
        body.dark-mode .chat-entry { border-color: #4a5e72; }
        body.dark-mode .chat-entry:hover { background: #3b4a5a; }
        .chat-entry summary { cursor: pointer; font-weight: bold; margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center; }
        .chat-entry p { margin: 5px 0; max-height: 100px; overflow-y: auto; }
        .chat-timestamp { font-size: 12px; color: #666; margin-bottom: 5px; }
        body.dark-mode .chat-timestamp { color: #b0b0b0; }
        .delete-chat { background: #d32f2f; padding: 4px 8px; font-size: 12px; }
        .delete-chat:hover { background: #b71c1c; }
        .clear-history { background: #d32f2f; margin-bottom: 15px; }
        .clear-history:hover { background: #b71c1c; }
        .chat-search { margin-bottom: 15px; }
        .chat-search input { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
        body.dark-mode .chat-search input { background: #3b4a5a; color: #e0e0e0; border-color: #4a5e72; }
        .model-description { font-size: 12px; color: #666; margin-top: 5px; }
        body.dark-mode .model-description { color: #b0b0b0; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        .logo { display: flex; align-items: center; gap: 10px; }
        .logo-text { font-size: 20px; font-weight: bold; color: #007aff; text-transform: uppercase; letter-spacing: 1px; }
        body.dark-mode .logo-text { color: #66b0ff; }
        .logo-icon { width: 30px; height: 30px; background: linear-gradient(45deg, #007aff, #66b0ff); border-radius: 4px; display: flex; align-items: center; justify-content: center; color: white; font-size: 16px; font-weight: bold; }
        .error-message { color: #d32f2f; margin-top: 10px; font-size: 14px; }
        .success-message { color: #2e7d32; margin-top: 10px; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>CSV Search + AI</h1>
            <div class="logo">
                <div class="logo-icon">CSV</div>
                <div class="logo-text">Tools</div>
            </div>
        </div>
        <!-- Settings and Theme Toggle -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <button id="settingsBtn">Settings</button>
            <button id="darkModeBtn">Toggle Dark Mode</button>
            <button id="chatHistoryBtn">Chat History</button>
        </div>
        <!-- Settings Modal -->
        <div id="settingsModal" class="modal">
            <div class="modal-content">
                <h2>Settings</h2>
                <form id="settingsForm" method="post" action="{{ url_for('settings') }}" enctype="multipart/form-data">
                    <label>Current CSV File:</label>
                    <p>{{ current_csv_path }}</p>
                    <label>Upload New CSV File:</label>
                    <input type="file" name="csv_file" id="csvFileInput" accept=".csv">
                    <!-- Removed Search Column field per request -->
                    <label>Rows Per Page:</label>
                    <input type="number" name="rows_per_page" id="rowsPerPageInput" value="{{ current_rows_per_page }}" min="1" max="100">
                    <label>AI Model:</label>
                    <select name="model" id="modelSelect">
                        <option value="gemini-2.5-pro-exp-03-25" {% if current_model == 'gemini-2.5-pro-exp-03-25' %}selected{% endif %}>Gemini 2.5 Pro</option>
                        <option value="gemini-2.0-flash" {% if current_model == 'gemini-2.0-flash' %}selected{% endif %}>Gemini 2.0 Flash</option>
                        <option value="gemini-2.0-flash-lite" {% if current_model == 'gemini-2.0-flash-lite' %}selected{% endif %}>Gemini 2.0 Flash Lite</option>
                        <option value="gemini-2.0-flash-thinking-exp-01-21" {% if current_model == 'gemini-2.0-flash-thinking-exp-01-21' %}selected{% endif %}>Gemini 2.0 Flash Thinking</option>
                    </select>
                    <div class="model-description" id="modelDescription"></div>
                    <label>API Key:</label>
                    <input type="text" name="api_key" value="{{ current_api_key }}" placeholder="Enter your API key here">
                    <!-- Hidden input for dark mode state -->
                    <input type="hidden" name="dark_mode" id="darkModeInput" value="">
                    <div style="display: flex; gap: 10px;">
                        <input type="submit" value="Save">
                        <button type="button" id="cancelSettingsBtn">Cancel</button>
                    </div>
                    <p style="font-size: 12px; text-align: center; color: gray;">Powered by Jose Espinosa by AE1O1, owned by Ahmed Elhadi © 2025<br>jpm.onestop@gmail.com</p>
                </form>
            </div>
        </div>
        <!-- Chat History Sidebar -->
        <div class="sidebar" id="chatSidebar">
            <h3>Chat History</h3>
            <div class="chat-search">
                <input type="text" id="chatSearchInput" placeholder="Search chat history..." onkeyup="filterChatHistory()">
            </div>
            <button class="clear-history" id="clearHistoryBtn">Clear History</button>
            <div id="chatHistory">
                {% for entry in chat_history %}
                    <details class="chat-entry" data-id="{{ entry.id }}" data-query="{{ entry.query | lower }}">
                        <summary>
                            <span>{{ entry.query }}</span>
                            <button class="delete-chat" onclick="deleteChatEntry({{ entry.id }})">Delete</button>
                        </summary>
                        <div class="chat-timestamp">{{ entry.timestamp }}</div>
                        <p>{{ entry.response | safe }}</p>
                    </details>
                {% endfor %}
            </div>
        </div>
        <!-- Search Form -->
        <!-- Updated label to reflect searching across all columns -->
        <form id="searchForm">
            <label>Search in all columns:</label><br>
            <input type="text" id="searchQuery" required>
            <input type="submit" value="Search">
        </form>
        <!-- AI Query Section -->
        <div id="aiQuerySection" style="display:none; margin-top: 20px;">
            <form id="aiForm">
                <label>Ask AI:</label><br>
                <input type="text" id="aiQuery" required>
                <input type="submit" value="Ask AI">
            </form>
        </div>
        <!-- New Search and Export Buttons -->
        <div style="display: flex; gap: 10px; margin-top: 10px;">
            <button id="newSearchBtn" style="display:none;">New Search</button>
            <button id="exportBtn" style="display:none;">Export as CSV</button>
        </div>
        <!-- Display Options -->
        <div class="options" id="displayOptions" style="display:none;">
            <div>
                <label>Table Text Wrap:</label>
                <select id="tableWrap" onchange="updateDisplayOptions()">
                    <option value="wrap">Wrap</option>
                    <option value="nowrap">No Wrap</option>
                </select>
            </div>
            <div>
                <label>AI Response Text Wrap:</label>
                <select id="aiWrap" onchange="updateDisplayOptions()">
                    <option value="wrap">Wrap</option>
                    <option value="nowrap">No Wrap</option>
                </select>
            </div>
        </div>
        <!-- AI Response -->
        <div id="aiResponse"></div>
        <!-- Search Results -->
        <div id="searchResults" class="table-container"></div>
        <!-- Pagination -->
        <div class="pagination" id="pagination" style="display:none;"></div>
        <!-- Loading Overlay -->
        <div id="loadingOverlay"><div>Loading...</div></div>
        <!-- Success/Error Messages -->
        {% if success_message %}
            <div class="success-message">{{ success_message }}</div>
        {% endif %}
        {% if error_message %}
            <div class="error-message">{{ error_message }}</div>
        {% endif %}
    </div>
    <footer>
        <a href="https://github.com/xraisen/CSV-Tools" target="_blank">GitHub Repository</a>
    </footer>
    <script>
        let currentPage = 1;
        let totalPages = 1;
        let isDarkMode = {{ 'true' if dark_mode else 'false' }} || localStorage.getItem('darkMode') === 'true';

        const modelDescriptions = {
            "gemini-2.5-pro-exp-03-25": "Best for Coding, Reasoning, Multimodal understanding. Pricing: $0.00/$0.00",
            "gemini-2.0-flash": "Best for Multimodal understanding, Realtime streaming, Native tool use. Pricing: $0.075/$0.30",
            "gemini-2.0-flash-lite": "Best for Long Context, Realtime streaming, Native tool use. Pricing: $0.075/$0.30",
            "gemini-2.0-flash-thinking-exp-01-21": "Best for Multimodal understanding, Reasoning, Coding. Pricing: $0.00/$0.00"
        };

        document.addEventListener('DOMContentLoaded', () => {
            if (isDarkMode) {
                document.body.classList.add('dark-mode');
            }

            document.getElementById('settingsBtn').addEventListener('click', () => {
                document.getElementById('settingsModal').style.display = 'block';
            });

            document.getElementById('cancelSettingsBtn').addEventListener('click', () => {
                document.getElementById('settingsModal').style.display = 'none';
            });

            document.getElementById('darkModeBtn').addEventListener('click', toggleDarkMode);
            document.getElementById('chatHistoryBtn').addEventListener('click', toggleChatHistory);
            document.getElementById('clearHistoryBtn').addEventListener('click', clearChatHistory);

            document.getElementById('searchForm').addEventListener('submit', (event) => {
                event.preventDefault();
                doSearch();
            });

            document.getElementById('aiForm').addEventListener('submit', (event) => {
                event.preventDefault();
                doAIQuery();
            });

            document.getElementById('newSearchBtn').addEventListener('click', () => {
                newSearch();
            });

            document.getElementById('exportBtn').addEventListener('click', () => {
                exportCSV();
            });

            document.getElementById('settingsForm').addEventListener('submit', () => {
                document.getElementById('darkModeInput').value = isDarkMode;
            });

            document.getElementById('csvFileInput').addEventListener('change', previewCsvHeaders);
            updateModelDescription();
            document.getElementById('modelSelect').addEventListener('change', updateModelDescription);
        });

        async function previewCsvHeaders() {
            const fileInput = document.getElementById('csvFileInput');
            if (fileInput.files.length === 0) return;
            const formData = new FormData();
            formData.append('csv_file', fileInput.files[0]);
            try {
                const response = await fetch('/preview_csv_headers', { method: 'POST', body: formData });
                const data = await response.json();
                if (data.error) {
                    showError(data.error);
                    return;
                }
            } catch (err) {
                console.error('Error previewing CSV headers:', err);
                showError('Failed to preview CSV headers: ' + err.message);
            }
        }

        function updateModelDescription() {
            const model = document.getElementById('modelSelect').value;
            document.getElementById('modelDescription').textContent = modelDescriptions[model] || '';
        }

        async function doSearch() {
            const query = document.getElementById('searchQuery').value.trim();
            if (!query) {
                showError('Please enter a search query.');
                return;
            }
            showLoading(true);
            try {
                currentPage = 1;
                const response = await fetch('/search', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: query, page: currentPage})
                });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                showLoading(false);
                if (data.error) {
                    showError(data.error);
                    return;
                }
                document.getElementById('searchResults').innerHTML = data.html;
                totalPages = data.total_pages;
                updatePagination();
                document.getElementById('aiQuerySection').style.display = 'block';
                document.getElementById('newSearchBtn').style.display = 'block';
                document.getElementById('exportBtn').style.display = 'block';
                document.getElementById('displayOptions').style.display = 'block';
                document.getElementById('pagination').style.display = totalPages > 1 ? 'flex' : 'none';
                document.getElementById('aiResponse').innerHTML = '';
                updateDisplayOptions();
                sessionStorage.setItem('currentQuery', query);
            } catch (err) {
                handleError(err);
            }
        }

        async function doAIQuery() {
            const userQuery = document.getElementById('aiQuery').value.trim();
            if (!userQuery) {
                showError('Please enter an AI query.');
                return;
            }
            showLoading(true);
            try {
                const response = await fetch('/ai_query', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({userQuery: userQuery})
                });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                showLoading(false);
                const aiResponseDiv = document.getElementById('aiResponse');
                const newResponse = document.createElement('div');
                newResponse.innerHTML = data.ai_html;
                aiResponseDiv.appendChild(newResponse);
                aiResponseDiv.scrollTop = aiResponseDiv.scrollHeight;
                if (data.chat_html) {
                    document.getElementById('chatHistory').innerHTML = data.chat_html;
                    filterChatHistory();
                }
                const actionScript = newResponse.querySelector('script[type="ai-action"]');
                if (actionScript) {
                    const scriptContent = actionScript.textContent.trim();
                    try {
                        const action = JSON.parse(scriptContent);
                        if (action) {
                            const response = await fetch('/manipulate_table', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({action: action, page: currentPage})
                            });
                            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                            const data = await response.json();
                            if (data.html) {
                                document.getElementById('searchResults').innerHTML = data.html;
                                totalPages = data.total_pages;
                                updatePagination();
                                updateDisplayOptions();
                            }
                        }
                    } catch (e) {
                        console.error('Error parsing AI action:', e);
                        showError('Failed to process AI action: ' + e.message);
                    }
                }
            } catch (err) {
                handleError(err);
            }
        }

        async function sortColumn(column) {
            const action = { action: 'sort', column: column, order: 'ascending' };
            showLoading(true);
            try {
                const response = await fetch('/manipulate_table', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({action: action, page: currentPage})
                });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                showLoading(false);
                document.getElementById('searchResults').innerHTML = data.html;
                totalPages = data.total_pages;
                updatePagination();
                updateDisplayOptions();
            } catch (err) {
                handleError(err);
            }
        }

        async function changePage(page) {
            if (page < 1 || page > totalPages) return;
            currentPage = page;
            showLoading(true);
            try {
                const query = sessionStorage.getItem('currentQuery');
                if (!query) throw new Error('No search query found for pagination.');
                const response = await fetch('/search', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({query: query, page: currentPage})
                });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                showLoading(false);
                if (data.error) {
                    showError(data.error);
                    return;
                }
                document.getElementById('searchResults').innerHTML = data.html;
                updatePagination();
                updateDisplayOptions();
            } catch (err) {
                handleError(err);
            }
        }

        function updatePagination() {
            const pagination = document.getElementById('pagination');
            pagination.innerHTML = '';
            const prevButton = document.createElement('button');
            prevButton.textContent = 'Previous';
            prevButton.disabled = currentPage === 1;
            prevButton.addEventListener('click', () => changePage(currentPage - 1));
            pagination.appendChild(prevButton);
            for (let i = 1; i <= totalPages; i++) {
                const pageButton = document.createElement('button');
                pageButton.textContent = i;
                if (i === currentPage) {
                    pageButton.style.background = '#005bb5';
                }
                pageButton.addEventListener('click', () => changePage(i));
                pagination.appendChild(pageButton);
            }
            const nextButton = document.createElement('button');
            nextButton.textContent = 'Next';
            nextButton.disabled = currentPage === totalPages;
            nextButton.addEventListener('click', () => changePage(currentPage + 1));
            pagination.appendChild(nextButton);
        }

        function exportCSV() {
            window.location.href = '/export';
        }

        async function newSearch() {
            document.getElementById('searchResults').innerHTML = '';
            document.getElementById('aiResponse').innerHTML = '';
            document.getElementById('aiQuerySection').style.display = 'none';
            document.getElementById('newSearchBtn').style.display = 'none';
            document.getElementById('exportBtn').style.display = 'none';
            document.getElementById('displayOptions').style.display = 'none';
            document.getElementById('pagination').style.display = 'none';
            document.getElementById('searchQuery').value = '';
            sessionStorage.removeItem('currentQuery');
            try {
                const response = await fetch('/reset');
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            } catch (err) {
                console.error('Error resetting session:', err);
                showError('Failed to reset search. Please try again.');
            }
        }

        async function clearChatHistory() {
            try {
                const response = await fetch('/clear_chat_history');
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                document.getElementById('chatHistory').innerHTML = data.html;
                document.getElementById('chatSearchInput').value = '';
            } catch (err) {
                console.error('Error clearing chat history:', err);
                showError('Failed to clear chat history. Please try again.');
            }
        }

        async function deleteChatEntry(id) {
            try {
                const response = await fetch('/delete_chat_entry', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({id: id})
                });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data = await response.json();
                document.getElementById('chatHistory').innerHTML = data.html;
                filterChatHistory();
            } catch (err) {
                console.error('Error deleting chat entry:', err);
                showError('Failed to delete chat entry. Please try again.');
            }
        }

        function filterChatHistory() {
            const searchText = document.getElementById('chatSearchInput').value.toLowerCase();
            const chatEntries = document.querySelectorAll('.chat-entry');
            chatEntries.forEach(entry => {
                const query = entry.getAttribute('data-query');
                entry.style.display = query.includes(searchText) ? 'block' : 'none';
            });
        }

        function showLoading(show) {
            document.getElementById('loadingOverlay').style.display = show ? 'block' : 'none';
        }

        function handleError(err) {
            showLoading(false);
            console.error('Error:', err);
            showError('An error occurred: ' + err.message);
        }

        function showError(message) {
            const errorDiv = document.createElement('div');
            errorDiv.className = 'error-message';
            errorDiv.textContent = message;
            const container = document.querySelector('.container');
            const existingError = container.querySelector('.error-message');
            if (existingError) existingError.remove();
            container.insertBefore(errorDiv, container.firstChild);
            setTimeout(() => errorDiv.remove(), 5000);
        }

        function showSuccess(message) {
            const successDiv = document.createElement('div');
            successDiv.className = 'success-message';
            successDiv.textContent = message;
            const container = document.querySelector('.container');
            const existingSuccess = container.querySelector('.success-message');
            if (existingSuccess) existingSuccess.remove();
            container.insertBefore(successDiv, container.firstChild);
            setTimeout(() => successDiv.remove(), 5000);
        }

        function updateDisplayOptions() {
            const tableWrap = document.getElementById('tableWrap').value;
            const aiWrap = document.getElementById('aiWrap').value;
            const tableCells = document.querySelectorAll('#searchResults td, #searchResults th');
            const aiResponse = document.getElementById('aiResponse');
            tableCells.forEach(cell => {
                cell.style.whiteSpace = tableWrap === 'wrap' ? 'normal' : 'nowrap';
            });
            aiResponse.style.whiteSpace = aiWrap === 'wrap' ? 'normal' : 'nowrap';
        }

        function toggleDarkMode() {
            isDarkMode = !isDarkMode;
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('darkMode', isDarkMode);
        }

        function toggleChatHistory() {
            const sidebar = document.getElementById('chatSidebar');
            sidebar.classList.toggle('open');
        }

        document.addEventListener('click', (event) => {
            const sidebar = document.getElementById('chatSidebar');
            const toggleButton = event.target.closest('#chatHistoryBtn');
            if (!sidebar.contains(event.target) && !toggleButton && sidebar.classList.contains('open')) {
                sidebar.classList.remove('open');
            }
        });

        document.addEventListener('click', (event) => {
            const modal = document.getElementById('settingsModal');
            const modalContent = modal.querySelector('.modal-content');
            const toggleButton = event.target.closest('#settingsBtn');
            if (modal.style.display === 'block' && !modalContent.contains(event.target) && !toggleButton) {
                modal.style.display = 'none';
            }
        });
    </script>
</body>
</html>
"""

# --- Flask Routes ---
@app.route('/')
def index():
    if 'csv_path' not in session:
        session['csv_path'] = persistent_settings.get('csv_path', DEFAULT_CSV_PATH)
    if 'model' not in session:
        session['model'] = persistent_settings.get('model', 'gemini-2.0-flash-thinking-exp-01-21')
    if 'rows_per_page' not in session:
        session['rows_per_page'] = persistent_settings.get('rows_per_page', DEFAULT_ROWS_PER_PAGE)
    if 'api_key' not in session:
        session['api_key'] = None
    if 'chat_history' not in session:
        session['chat_history'] = persistent_chat_history

    current_csv_path = session['csv_path']
    current_model = session['model']
    current_rows_per_page = session['rows_per_page']
    current_api_key = '' if session['api_key'] is None else session['api_key']
    dark_mode = persistent_settings.get('dark_mode', False)
    chat_history = session['chat_history']
    csv_columns = get_csv_columns(current_csv_path)

    success_message = session.pop('success_message', None)
    error_message = session.pop('error_message', None)

    return render_template_string(
        HTML_TEMPLATE,
        current_csv_path=current_csv_path,
        current_model=current_model,
        current_api_key=current_api_key,
        current_rows_per_page=current_rows_per_page,
        dark_mode=dark_mode,
        chat_history=chat_history,
        csv_columns=csv_columns,
        success_message=success_message,
        error_message=error_message
    )

@app.route('/settings', methods=['POST'])
def settings():
    if 'csv_file' in request.files and request.files['csv_file'].filename:
        file = request.files['csv_file']
        if not file.filename.endswith('.csv'):
            session['error_message'] = 'Please upload a CSV file.'
            return redirect(url_for('index'))
        filename = f"uploaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        session['csv_path'] = file_path
    else:
        session['csv_path'] = session.get('csv_path', DEFAULT_CSV_PATH)
    
    session['model'] = request.form.get('model')
    api_key = request.form.get('api_key', '').strip()
    if api_key:
        session['api_key'] = api_key
    rows_per_page = int(request.form.get('rows_per_page', DEFAULT_ROWS_PER_PAGE))
    if rows_per_page < 1 or rows_per_page > 100:
        session['error_message'] = 'Rows per page must be between 1 and 100.'
        return redirect(url_for('index'))
    session['rows_per_page'] = rows_per_page
    
    dark_mode = request.form.get('dark_mode', 'false').lower() == 'true'
    persistent_settings.update({
        'csv_path': session['csv_path'],
        'model': session['model'],
        'dark_mode': dark_mode,
        'rows_per_page': session['rows_per_page']
    })
    save_settings(persistent_settings)
    
    session['success_message'] = 'Settings saved successfully.'
    return redirect(url_for('index'))

@app.route('/search', methods=['POST'])
def search():
    query = request.json.get('query', '').strip()
    page = request.json.get('page', 1)
    csv_path = session.get('csv_path', DEFAULT_CSV_PATH)
    if not query:
        return jsonify({"error": "Search query cannot be empty."})
    if not os.path.exists(csv_path):
        return jsonify({"html": "<p style='color:red;'>CSV file not found.</p>", "total_pages": 1})
    search_results = chunk_search_csv(csv_path, query)
    if not search_results and not get_csv_columns(csv_path):
        return jsonify({"error": "No matching columns found in CSV file."})
    html, summary, total_pages = generate_table_html(search_results, page)
    session['search_summary'] = summary
    session['last_query'] = query
    return jsonify({"html": html, "total_pages": total_pages})

@app.route('/ai_query', methods=['POST'])
def ai_query():
    user_query = request.json.get('userQuery', '').strip()
    if not user_query:
        return jsonify({"error": "AI query cannot be empty."})
    search_summary = session.get('search_summary', {'num_rows': 0, 'sample_rows': [], 'columns': []})
    last_query = session.get('last_query', '')
    ai_result = get_ai_response(search_summary, user_query, last_query)
    return jsonify({"ai_html": ai_result['response'], "chat_html": ai_result['chat_html']})

@app.route('/manipulate_table', methods=['POST'])
def manipulate_table():
    action = request.json.get('action')
    page = request.json.get('page', 1)
    query = session.get('last_query', '')
    if not query:
        return jsonify({"html": "<p>No search query available to manipulate.</p>", "total_pages": 1})
    csv_path = session.get('csv_path', DEFAULT_CSV_PATH)
    if not os.path.exists(csv_path):
        return jsonify({"html": "<p style='color:red;'>CSV file not found.</p>", "total_pages": 1})
    search_results = chunk_search_csv(csv_path, query)
    if not search_results and not get_csv_columns(csv_path):
        return jsonify({"error": "No matching columns found in CSV file."})
    search_results = manipulate_results(search_results, action)
    html, _, total_pages = generate_table_html(search_results, page)
    return jsonify({"html": html, "total_pages": total_pages})

@app.route('/export', methods=['GET', 'POST'])
def export_csv():
    csv_path = session.get('csv_path', DEFAULT_CSV_PATH)
    if not csv_path:
        return jsonify({'error': 'No CSV file selected'}), 400
    if not os.path.exists(csv_path):
        return jsonify({'error': f'CSV file not found at path: {csv_path}'}), 400
    
    # Get current search results if available
    current_results = session.get('search_results', session.get('current_results', []))
    
    if current_results:
        # Export current view including combined columns
        df = pd.DataFrame([r['data'] for r in current_results])
        
        # Apply column selections from session if they exist
        if 'columns' in session and session['columns']:
            available_columns = [col for col in session['columns'] if col in df.columns]
            if available_columns:
                df = df[available_columns]
        # Include custom columns if they exist
        if 'custom_columns' in session and session['custom_columns']:
            for col_name, col_data in session['custom_columns'].items():
                if col_name not in df.columns:
                    df[col_name] = col_data
        # Ensure original columns are preserved if no custom selections exist
        elif 'original_columns' in session:
            df = df[session['original_columns']]
    else:
        # Fall back to original CSV if no current results
        df = load_csv_cached(csv_path)
        
        # Apply column selections from session if they exist
        if 'columns' in session and session['columns']:
            available_columns = [col for col in session['columns'] if col in df.columns]
            if available_columns:
                df = df[available_columns]
        # Include custom columns if they exist
        if 'custom_columns' in session and session['custom_columns']:
            for col_name, col_data in session['custom_columns'].items():
                if col_name not in df.columns:
                    df[col_name] = col_data
        # Ensure original columns are preserved if no custom selections exist
        elif 'original_columns' in session:
            df = df[session['original_columns']]
    
    if df.empty:
        return jsonify({'error': 'No data to export'}), 400
    
    # Create output in memory
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

@app.route('/clear_chat_history')
def clear_chat_history():
    session['chat_history'] = []
    save_chat_history([])
    return jsonify({"html": ""})

@app.route('/delete_chat_entry', methods=['POST'])
def delete_chat_entry():
    entry_id = request.json.get('id')
    chat_history = session.get('chat_history', [])
    chat_history = [entry for entry in chat_history if entry['id'] != entry_id]
    session['chat_history'] = chat_history
    save_chat_history(chat_history)
    html = ''
    for entry in chat_history:
        html += (
            f'<details class="chat-entry" data-id="{entry["id"]}" data-query="{entry["query"].lower()}">'
            f'<summary><span>{entry["query"]}</span><button class="delete-chat" onclick="deleteChatEntry({entry["id"]})">Delete</button></summary>'
            f'<div class="chat-timestamp">{entry["timestamp"]}</div>'
            f'<p>{entry["response"]}</p>'
            '</details>'
        )
    return jsonify({"html": html})

@app.route('/reset')
def reset():
    session.pop('search_summary', None)
    session.pop('last_query', None)
    return "OK"

def generate_table_html(search_results, page=1):
    if not search_results:
        return "<p>No results found.</p>", {'num_rows': 0, 'sample_rows': [], 'columns': []}, 1
    rows_per_page = session.get('rows_per_page', DEFAULT_ROWS_PER_PAGE)
    total_rows = len(search_results)
    total_pages = (total_rows + rows_per_page - 1) // rows_per_page
    start = (page - 1) * rows_per_page
    end = start + rows_per_page
    paginated_results = search_results[start:end]
    if not paginated_results:
        return "<p>No results on this page.</p>", {'num_rows': 0, 'sample_rows': [], 'columns': []}, total_pages
    columns = list(paginated_results[0]['data'].keys())
    table_html = "<table><tr><th>Row #</th>"
    for col in columns:
        table_html += f"<th onclick=\"sortColumn('{col}')\">{col}</th>"
    table_html += "</tr>"
    for result in paginated_results:
        row_index = result['row_index']
        row_data = result['data']
        matching_columns = result['matching_columns']
        table_html += f"<tr><td>{row_index}</td>"
        for col in columns:
            cell_val = row_data.get(col, '')
            highlight = "highlight" if col in matching_columns else ""
            table_html += f"<td class='{highlight}'>{cell_val}</td>"
        table_html += "</tr>"
    table_html += "</table>"
    sample_rows = [{'row_index': r['row_index'], **r['data']} for r in search_results[:5]]
    summary = {'num_rows': len(search_results), 'sample_rows': sample_rows, 'columns': columns}
    return f"<h2>Search Results</h2>{table_html}", summary, total_pages

#if __name__ == '__main__':
#    def run_app():
#        app.run(debug=True, use_reloader=False)
#    threading.Thread(target=run_app).start()
#    webbrowser.open('http://127.0.0.1:5000/')
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Use PORT env var or default to 5000
    app.run(host="0.0.0.0", port=port, debug=False)  # Bind to 0.0.0.0 for external access
