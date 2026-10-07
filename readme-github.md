# Verified Data Agent 🔎

A Streamlit application that uses Google Gemini to analyze uploaded data (CSV, Excel, or PDF) and strictly verifies answers by generating and executing sandboxed Pandas code.

---

## Features

* **Multi-Format Data Support**: Ingests CSV (`.csv`), Excel (`.xlsx`, `.xls`), and PDF (`.pdf`) files with automatic extraction of tables and plain text.
* **Strict Grounding**: Configured with system instructions to rely strictly on supplied data and refuse hallucinated or unverifiable answers.
* **Executable Code Generation**: Generates pure Pandas/Python code to compute answers rather than predicting raw numerical values directly.
* **AST Code Validation**: Validates generated code using Python's Abstract Syntax Tree (AST) to restrict non-whitelisted imports, blocked function calls (e.g., `eval`, `exec`), and unsafe module imports.
* **Isolated Local Execution**: Executes data transformations in an isolated process via `subprocess` with execution timeouts and Pandas pickle deserialization.
* **Fallback & Retry Logic**: Includes automated retry handling with exponential backoff for Gemini API overloads (status codes 429, 500, 502, 503, 504) and fallback model support.

---

## Repository Structure

```text
.
├── app.py              # Main Streamlit application and execution agent
├── requirements.txt    # Project dependencies
├── .env.example        # Environment variable template
└── readme_md.md           # Project documentation
