# Verified Data Agent 🔎

A Streamlit application that answers questions over uploaded CSV, Excel, and PDF data by using Google Gemini to generate Pandas code and executing it locally to verify all analytical results.

---

## 🌟 Key Features

* **Multi-Format Data Support**: Ingests CSV (`.csv`), Excel (`.xlsx`, `.xls`), and PDF (`.pdf`) files with automatic extraction of tables and plain text.
* **Strict Data Grounding**: Configured with system instructions to rely strictly on supplied data and refuse hallucinated or unverifiable answers.
* **Executable Verification**: Generates pure Pandas/Python code to compute answers rather than predicting raw numerical values directly.
* **AST Code Safety Validation**: Validates generated code using Python's Abstract Syntax Tree (`ast`) to block unauthorized imports, system execution, and dangerous built-ins (`eval`, `exec`, `open`, `os`, `subprocess`).
* **Sandboxed Subprocess Execution**: Executes code in an isolated subprocess with explicit timeout safeguards and Pandas pickle deserialization.
* **API Retry & Fallback**: Includes automated retry logic with exponential backoff for Gemini API rate limits (status codes 429, 500, 502, 503, 504) and fallback model support.

---

## 🔄 Workflow

```text
[Upload CSV / Excel / PDF]
          │
          ▼
[Pandas / pdfplumber Extraction]
          │
          ▼
[Gemini Generates Pandas Code]
          │
          ▼
[AST Safety Code Inspector]
          │
          ▼
[Subprocess Execution & Verification]
          │
          ▼
[Gemini Explains Executed Result]
```

---

## 📁 Repository Structure

```text
.
├── app.py              # Main Streamlit application and execution agent
├── requirements.txt    # Project dependencies
├── .env.example        # Environment variable template
└── README.md           # Project documentation
```

---

## ⚙️ Requirements

* **Python**: `3.9` or higher
* **Gemini API Key**: Obtain a key from [Google AI Studio](https://aistudio.google.com/apikey).

---

## 🚀 Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/verified-data-agent.git
cd verified-data-agent
```

### 2. Create and Activate Virtual Environment

* **Windows:**
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate
  ```

* **macOS/Linux:**
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```

### 3. Install Dependencies

Create a `requirements.txt` file (if not present) with:

```text
streamlit
pandas
requests
pdfplumber
python-dotenv
openpyxl
```

Then install:

```bash
pip install -r requirements.txt
```

---

## 🔑 Environment Configuration

Create a `.env` file in the root directory:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash
```

> **Note:** You can also leave `GEMINI_API_KEY` empty in `.env` and enter your API key directly in the Streamlit app sidebar.

---

## 💻 Running the App

Launch the Streamlit application:

```bash
streamlit run app.py
```

Open `http://localhost:8501` in your browser.

---

## 🧪 Sample Test Case

1. Create a file named `sales.csv`:
   ```csv
   Customer_ID,City,Amount
   1,Chennai,1200
   2,Bangalore,800
   3,Chennai,1500
   4,Chennai,700
   ```

2. Upload `sales.csv` in the sidebar.
3. Ask the question:
   > *What is the total amount spent by customers from Chennai?*
4. The agent will run the verified Python code:
   ```python
   result = sales[sales['city'] == 'chennai']['amount'].sum()
   print(result)
   ```
5. **Verified Result Output:** `3400`

---

## 🛡️ Security Note

The included AST code inspector and subprocess isolated execution environment are designed for local prototyping. For production deployments, model-generated code should be executed within a dedicated containerized sandbox (e.g., Docker, gVisor, or WebAssembly) with strict CPU, memory, filesystem, and network restrictions.