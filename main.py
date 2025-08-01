# Read employee to-dos from Odoo hr.employee model
def get_odoo_employee_todos():
    # This assumes there is a field like 'todo_ids' or similar on hr.employee
    employees = odoo_models.execute_kw(
        config.ODOO_DB, odoo_uid, config.ODOO_PASSWORD,
        'hr.employee', 'search_read',
        [[]],
        {'fields': ['id', 'name', 'activity_ids']}
    )
    todos = []
    for emp in employees:
        if 'activity_ids' in emp and emp['activity_ids']:
            # Fetch activity details for each employee
            activity_details = odoo_models.execute_kw(
                config.ODOO_DB, odoo_uid, config.ODOO_PASSWORD,
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
import requests
import xmlrpc.client
from msal import ConfidentialClientApplication
import config

# --- Odoo XML-RPC Setup ---
odoo_common = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/common")
odoo_uid = odoo_common.authenticate(config.ODOO_DB, config.ODOO_USERNAME, config.ODOO_PASSWORD, {})
odoo_models = xmlrpc.client.ServerProxy(f"{config.ODOO_URL}/xmlrpc/2/object")

def get_odoo_tasks():
    # Read tasks from Odoo 'project.task' model
    tasks = odoo_models.execute_kw(
        config.ODOO_DB, odoo_uid, config.ODOO_PASSWORD,
        'project.task', 'search_read',
        [[]],
        {'fields': ['id', 'name', 'description', 'stage_id']}
    )
    return tasks

# --- Azure Graph API Setup ---
def get_azure_token():
    app = ConfidentialClientApplication(
        config.AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{config.AZURE_TENANT_ID}",
        client_credential=config.AZURE_CLIENT_SECRET
    )
    token = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return token.get("access_token")

def push_task_to_azure(access_token, task):
    # Use application permissions endpoint
    url = f"https://graph.microsoft.com/v1.0/users/{config.AZURE_USER_ID}/todo/lists/{config.AZURE_TODO_LIST_ID}/tasks"
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    # Check for existing task with same title
    get_url = url
    get_resp = requests.get(get_url, headers=headers)
    if get_resp.status_code == 200:
        items = get_resp.json().get("value", [])
        for item in items:
            if item.get("title", "").strip().lower() == task["name"].strip().lower():
                return 409, "Task already exists"
    data = {
        "title": task["name"],
        "body": {"content": task.get("description", ""), "contentType": "text"}
    }
    response = requests.post(url, headers=headers, json=data)
    return response.status_code, response.text

def main():
    # Discover available fields in hr.employee
    print("Discovering fields in hr.employee...")
    try:
        employee_fields = odoo_models.execute_kw(
            config.ODOO_DB, odoo_uid, config.ODOO_PASSWORD,
            'hr.employee', 'fields_get',
            [],
            {'attributes': ['string', 'help', 'type']}
        )
        print("hr.employee fields:")
        print(list(employee_fields.keys()))
    except Exception as e:
        print(f"Error discovering hr.employee fields: {e}")
    print("Reading tasks from Odoo project.task...")
    tasks = get_odoo_tasks()
    print(f"Found {len(tasks)} project tasks.")

    print("Reading employee to-dos from Odoo hr.employee...")
    employee_todos = get_odoo_employee_todos()
    print(f"Found {len(employee_todos)} employee to-dos.")
    access_token = get_azure_token()
    print("\nSyncing project tasks to Azure...")
    for task in tasks:
        status, resp = push_task_to_azure(access_token, task)
        print(f"Azure: Pushed project task '{task['name']}': {status}\nResponse: {resp}\n")

    print("Syncing employee to-dos to Azure...")
    for todo in employee_todos:
        # Use summary for title, note for description
        emp_task = {
            "name": todo.get("summary", ""),
            "description": todo.get("note", "")
        }
        status, resp = push_task_to_azure(access_token, emp_task)
        print(f"Azure: Pushed employee to-do '{emp_task['name']}': {status}\nResponse: {resp}\n")

    # Push to Google Tasks
    print("\nPushing project tasks to Google Tasks...")
    google_token = get_google_access_token()
    if google_token:
        google_tasklist_id = get_google_tasklist_id(google_token)
        if google_tasklist_id:
            for task in tasks:
                status, resp = push_task_to_google(google_token, google_tasklist_id, task)
                print(f"Google: Pushed project task '{task['name']}': {status}\nResponse: {resp}\n")
            print("Pushing employee to-dos to Google Tasks...")
            for todo in employee_todos:
                emp_task = {
                    "name": todo.get("summary", ""),
                    "description": todo.get("note", "")
                }
                status, resp = push_task_to_google(google_token, google_tasklist_id, emp_task)
                print(f"Google: Pushed employee to-do '{emp_task['name']}': {status}\nResponse: {resp}\n")
        else:
            print("Could not find Google tasklist.")
    else:
        print("Could not get Google access token.")

if __name__ == "__main__":
    main()
