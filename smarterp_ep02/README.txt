PROCUREMENT & INVENTORY MANAGEMENT - CONNECTED PROJECT

This folder contains the front end and Python Flask backend connected to an SQLite database.

FILES:
- procurement_inventory_frontend.html : Front end (HTML, CSS, JavaScript)
- app.py : Backend REST API
- requirements.txt : Python package list
- procurement_inventory.db : Created automatically when the server starts

SETUP ON WINDOWS:
1. Install Python 3 from https://www.python.org/downloads/ (enable Add Python to PATH).
2. Open this folder in VS Code.
3. Choose Terminal > New Terminal.
4. Run these commands one at a time:

   py -m venv .venv
   .venv\Scripts\activate
   py -m pip install -r requirements.txt
   py app.py

5. Keep the terminal open and browse to http://127.0.0.1:5000
6. Test http://127.0.0.1:5000/api/health

IMPORTANT:
- Open the app through http://127.0.0.1:5000, not by double-clicking the HTML file, because the page needs the backend API.
- SQLite data is saved in procurement_inventory.db in this folder.
- This is an educational demo; do not enter confidential real business data.
- GST calculations are estimates; verify applicable tax treatment for real transactions.
