# Fetch all models with planned activities (activity_ids) and sync their activities as Google Tasks
def get_all_model_activities():
    # Find all models with activity_ids field
    models = odoo_session.api_call(
        'ir.model.fields', 'search_read',
        [[['name', '=', 'activity_ids']]],
        {'fields': ['model']}
    )
    model_names = [m['model'] for m in models]
    print("\nModels with planned activity or todo:")
    for m in model_names:
        print(f" - {m}")
    # Fetch all activities for each model
    all_activities = []
    for model in model_names:
        try:
            records = odoo_session.api_call(
                model, 'search_read',
                [[['activity_ids', '!=', False]]],
                {'fields': ['id', 'name', 'activity_ids']}
            )
        except Exception as e:
            print(f"[WARNING] Skipping model '{model}' due to error: {e}")
            continue
        for rec in records:
            if rec.get('activity_ids'):
                try:
                    activity_details = odoo_session.api_call(
                        'mail.activity', 'read',
                        [rec['activity_ids']],
                        {'fields': ['id', 'summary', 'note', 'res_model', 'res_id']}
                    )
                except Exception as e:
                    print(f"[WARNING] Skipping activity_ids in model '{model}' record {rec.get('id')} due to error: {e}")
                    continue
                for act in activity_details:
                    desc = act.get('note', '')
                    if not isinstance(desc, str):
                        desc = ''
                    desc = f"Model: {act.get('res_model', '')} | Record ID: {act.get('res_id', '')}\n" + desc
                    all_activities.append({
                        "name": act.get("summary", "Planned Activity"),
                        "description": desc
                    })
    print(f"\nTotal planned activities found across all models: {len(all_activities)}")
    return all_activities
# Fetch inventory products from Odoo and format as tasks
def get_inventory_product_tasks():
    # Fetch products using Odoo's REST-like API endpoint
    url = f"{config.ODOO_URL}/web/dataset/call_kw/product.product/search_read"
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "model": "product.products",
            "method": "search_read",
            "args": [[['type', '=', 'product']]],
            "kwargs": {
                "fields": ['id', 'name', 'default_code', 'qty_available', 'lst_price', 'categ_id']
            }
        },
        "id": 1,
    }
    # Authenticate using basic auth (if Odoo allows) or session cookie
    # Here, use basic auth with username/password from config
    from requests.auth import HTTPBasicAuth
    resp = requests.post(url, headers=headers, data=json.dumps(payload), auth=HTTPBasicAuth(config.ODOO_USERNAME, config.ODOO_PASSWORD))
    resp.raise_for_status()
    result = resp.json()
    products = result.get('result', [])
    print(f"Fetched {len(products)} inventory products from Odoo:")
    tasks = []
    for prod in products:
        desc = f"Qty Available: {prod.get('qty_available', 0)}\nPrice: {prod.get('lst_price', 0)}"
        if prod.get('default_code'):
            desc += f"\nProduct Code: {prod['default_code']}"
        if prod.get('categ_id') and isinstance(prod['categ_id'], (list, tuple)) and len(prod['categ_id']) > 1:
            desc += f"\nCategory: {prod['categ_id'][1]}"
        print(f"  - {prod.get('name', 'Inventory Product')} | {desc.replace(chr(10), ' | ')}")
        tasks.append({
            "name": prod.get("name", "Inventory Product"),
            "description": desc
        })
    return tasks
odoo_uid = None
# Read project tasks from Odoo project.task model (API)
def get_odoo_tasks():
    tasks = odoo_session.api_call(
        'project.task', 'search_read',
        [[]],
        {'fields': ['id', 'name', 'description', 'stage_id']}
    )
    # Format for Google Tasks: use name as title, description as notes
    formatted_tasks = []
    for t in tasks:
        desc = t.get('description', '')
        if not isinstance(desc, str):
            desc = ''
        formatted_tasks.append({
            "name": t.get("name", "Project Task"),
            "description": desc
        })
    return formatted_tasks
import config
# Read planned maintenance activities from Odoo maintenance.request (API)
def get_odoo_maintenance_activities():
    # Only fetch requests with a planned date in the future
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    # domain: [('schedule_date', '>=', today)]
    activities = odoo_session.api_call(
        'maintenance.request', 'search_read',
        [[['schedule_date', '>=', today]]],
        {'fields': ['id', 'name', 'schedule_date', 'description', 'category_id', 'equipment_id']}
    )
    # Format for Google Tasks: use name as title, description as notes
    tasks = []
    for act in activities:
        desc = act.get('description', '')
        if not isinstance(desc, str):
            desc = ''
        cat = act.get('category_id')
        # Ignore Equipment field, only use desc (and optionally category/planned date)
        if cat and isinstance(cat, (list, tuple)) and len(cat) > 1:
            if isinstance(cat[1], str) and not isinstance(cat[1], bool) and cat[1]:
                desc = f"Category: {cat[1]}\n" + desc
            elif cat[1]:
                print(f"[DEBUG] Unexpected category_id value: {cat[1]} (type: {type(cat[1])})")
        if act.get('schedule_date'):
            desc = f"Planned: {act['schedule_date']}\n" + desc
        tasks.append({"name": act.get("name", "Maintenance Activity"), "description": desc})
    return tasks
import requests
import json
from urllib.parse import urlencode

# --- Odoo Session Auth Helper ---
class OdooSession:
    def __init__(self, url, db, username, password):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.authenticated = False

    def authenticate(self):
        auth_url = f"{self.url}/web/session/authenticate"
        headers = {"Content-Type": "application/json"}
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "db": self.db,
                "login": self.username,
                "password": self.password
            },
            "id": 1
        }
        resp = self.session.post(auth_url, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        result = resp.json()
        if 'result' in result and result['result'].get('uid'):
            self.authenticated = True
        else:
            raise Exception(f"Odoo session authentication failed: {result}")

    def api_call(self, model, method, args=None, kwargs=None):
        if not self.authenticated:
            self.authenticate()
        url = f"{self.url}/web/dataset/call_kw/{model}/{method}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "model": model,
                "method": method,
                "args": args or [],
                "kwargs": kwargs or {}
            },
            "id": 1
        }
        resp = self.session.post(url, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        result = resp.json()
        if 'result' in result:
            return result['result']
        else:
            raise Exception(f"Odoo API error: {result}")

# --- Odoo Authentication (login) ---
def odoo_login():
    url = f"{config.ODOO_URL}/jsonrpc"
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "method": "call",
        "params": {
            "service": "common",
            "method": "login",
            "args": [config.ODOO_DB, config.ODOO_USERNAME, config.ODOO_PASSWORD]
        },
        "id": 1
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload))
    resp.raise_for_status()
    result = resp.json()
    if 'result' in result:
        return result['result']
    else:
        raise Exception(f"Odoo login error: {result}")

# Read employee to-dos from Odoo hr.employee model (API)
def get_odoo_employee_todos():
    employees = odoo_session.api_call(
        'hr.employee', 'search_read',
        [[]],
        {'fields': ['id', 'name', 'activity_ids']}
    )
    todos = []
    for emp in employees:
        if 'activity_ids' in emp and emp['activity_ids']:
            activity_details = odoo_session.api_call(
                'mail.activity', 'read',
                [emp['activity_ids']],
                {'fields': ['id', 'summary', 'note']}
            )
            todos.extend(activity_details)
    return todos
import json
from urllib.parse import urlencode

# Google Tasks API integration
def get_google_access_token():
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "refresh_token": config.GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(token_url, data=data)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        print(f"Google token error: {response.status_code} {response.text}")
        return None

def get_google_tasklist_id(access_token):
    url = "https://tasks.googleapis.com/tasks/v1/users/@me/lists"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        lists = response.json().get("items", [])
        for l in lists:
            if l["title"].lower() == "tasks":
                return l["id"]
        if lists:
            return lists[0]["id"]
    print(f"Google tasklist error: {response.status_code} {response.text}")
    return None

def push_task_to_google(access_token, tasklist_id, task):
    # Check for existing task with same title (handle pagination)
    list_url = f"https://tasks.googleapis.com/tasks/v1/lists/{tasklist_id}/tasks"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    existing_titles = set()
    page_token = None
    while True:
        url = list_url
        if page_token:
            url += f"?pageToken={page_token}"
        get_resp = requests.get(url, headers=headers)
        if get_resp.status_code != 200:
            break
        resp_json = get_resp.json()
        items = resp_json.get("items", [])
        for item in items:
            title = item.get("title", "").strip().lower()
            existing_titles.add(title)
        page_token = resp_json.get("nextPageToken")
        if not page_token:
            break
    if task["name"].strip().lower() in existing_titles:
        return 409, "Task already exists"
    notes = task.get("description", "")
    if not isinstance(notes, str):
        notes = ""
    data = {
        "title": task["name"],
        "notes": notes
    }
    response = requests.post(list_url, headers=headers, json=data)
    return response.status_code, response.text



def main():
    global odoo_session
    odoo_session = OdooSession(config.ODOO_URL, config.ODOO_DB, config.ODOO_USERNAME, config.ODOO_PASSWORD)
    odoo_session.authenticate()

    # Push to Google Tasks
    print("\nPushing all planned activities from all models to Google Tasks...")
    google_token = get_google_access_token()
    if google_token:
        google_tasklist_id = get_google_tasklist_id(google_token)
        if google_tasklist_id:
            all_activities = get_all_model_activities()
            for act in all_activities:
                status, resp = push_task_to_google(google_token, google_tasklist_id, act)
                print(f"Google: Pushed planned activity '{act['name']}': {status}\nResponse: {resp}\n")
        else:
            print("Could not find Google tasklist.")
    else:
        print("Could not get Google access token.")

if __name__ == "__main__":
    main()
