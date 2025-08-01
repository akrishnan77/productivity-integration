# TasksSynch

Synchronize tasks from Odoo ERP to Microsoft To Do (Azure tenant) using Python.

## Features
- Reads tasks from Odoo using XML-RPC or REST API
- Pushes tasks to Microsoft To Do via Microsoft Graph API

## Setup
1. Configure Odoo and Azure credentials in `config.py`.
2. Run `main.py` to synchronize tasks.

## Requirements
- Python 3.8+
- `requests`, `xmlrpc.client`, `msal` (for Azure authentication)

## Usage
```bash
python main.py
```
