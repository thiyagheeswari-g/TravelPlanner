# TravelPlanner AI 🌍

A professional AI-driven travel planning dashboard with a Python backend and a React (Vite) frontend.

## 🚀 Getting Started

If you have just downloaded or cloned this repository, follow these steps to get the project running on your local machine.

### 1. Prerequisites
- **Python 3.8+**
- **Node.js 18+**
- **Git**

---

### 2. Backend Setup (Python)

The backend handles the AI logic, database management, and travel data processing.

1.  **Create a Virtual Environment**:
    ```bash
    python -m venv venv
    ```
2.  **Activate the Virtual Environment**:
    - Windows: `venv\Scripts\activate`
    - Mac/Linux: `source venv/bin/activate`
3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Environment Variables**:
    - Copy `.env.example` to a new file named `.env`.
    - Add your `HUGGINGFACEHUB_API_TOKEN` to the `.env` file.
5.  **Run the Backend**:
    ```bash
    python app.py
    ```

---

### 3. Frontend Setup (React + Vite)

The frontend is a modern, responsive dashboard built with React.

1.  **Navigate to the frontend folder**:
    ```bash
    cd frontend
    ```
2.  **Install Dependencies**:
    ```bash
    npm install
    ```
3.  **Run the Frontend**:
    ```bash
    npm run dev
    ```
4.  **Open in Browser**:
    Follow the link shown in your terminal (usually `http://localhost:5173`).

---

### 4. Project Structure
- `/dataset`: Contains JSON files for hotels, food, and attractions (Tracked in Git).
- `travel_planner.db`: The SQLite database (Tracked in Git).
- `app.py`: Main FastAPI/Flask entry point.
- `/frontend`: React source code.

## 📝 Note on Git
Files like `node_modules`, `venv`, and `.env` are **ignored** by Git to keep the repository lightweight and secure. Every new developer must install them locally using the steps above.
