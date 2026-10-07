import os
import re
import io
import json
import ast
import tempfile
import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import requests

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================
# STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Verified Data Agent",
    page_icon="🔎",
    layout="wide"
)


# ============================================================
# OLLAMA CONFIGURATION
# ============================================================

# Ollama runs on port 11434 by default.
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434"
).rstrip("/")

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3.2"
)

OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"

MAX_ROWS_IN_PROMPT = 30
EXEC_TIMEOUT = 8


# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are a careful data analyst.

You answer questions ONLY from the supplied data.

CRITICAL RULES:

1. Never invent missing values.

2. If the requested answer cannot be reliably derived from
   the supplied data, return can_answer=false.

3. Explain exactly what is missing or ambiguous when
   can_answer=false.

4. For numerical questions, generate executable Python code
   using pandas.

5. The code MUST compute the answer from the supplied
   dataframe variables.

6. NEVER hard-code the final answer.

7. The code MUST assign the final answer to a variable
   named `result`.

8. The code MUST print `result`.

9. Do not use network access.

10. Do not use subprocesses, shell commands, files,
    eval, exec, imports other than pandas/numpy/math.

11. Prefer simple and auditable operations:
    filtering, merging, grouping, aggregation,
    arithmetic and date parsing.

12. Be explicit about assumptions.

13. If an assumption could materially change the answer,
    set can_answer=false instead of guessing.

14. Return ONLY valid JSON.

Use exactly this structure:

{
  "can_answer": true,
  "answer_type": "number",
  "answer_summary": "short explanation",
  "code": "Python code",
  "reason": "why this answer is reliable"
}

answer_type must be one of:

"number"
"text"
"table"
"unknown"
"""


# ============================================================
# DATAFRAME HELPERS
# ============================================================

def dataframe_preview(df):
    sample = df.head(MAX_ROWS_IN_PROMPT).copy()
    return sample.to_csv(index=False)


def clean_code(raw):
    if not raw:
        return ""

    raw = raw.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:python)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    return raw.strip()


def extract_json(text):
    """
    Extract JSON from Ollama response.
    """

    if not text:
        raise ValueError("Ollama returned an empty response.")

    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object inside response
    start = text.find("{")
    end = text.rfind("}")

    if start >= 0 and end > start:
        candidate = text[start:end + 1]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Llama did not return valid JSON.\n\n"
        f"Raw response:\n{text}"
    )


# ============================================================
# OLLAMA CONNECTION
# ============================================================

def check_ollama():
    """
    Check whether Ollama is running and whether the requested
    model is installed.
    """

    try:
        response = requests.get(
            f"{OLLAMA_BASE_URL}/api/tags",
            timeout=5
        )

        response.raise_for_status()

        data = response.json()

        models = data.get("models", [])

        installed_models = []

        for model in models:
            name = model.get("name", "")
            installed_models.append(name)

        # Match llama3.2 with llama3.2:latest
        model_found = any(
            name == OLLAMA_MODEL
            or name.startswith(OLLAMA_MODEL + ":")
            for name in installed_models
        )

        return True, model_found, installed_models

    except requests.exceptions.ConnectionError:
        return False, False, []

    except Exception:
        return False, False, []


def call_ollama(prompt, system_prompt=None, json_mode=False):
    """
    Directly call Ollama.

    This DOES NOT use OpenAI.
    """

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [],
        "stream": False
    }

    if system_prompt:
        payload["messages"].append({
            "role": "system",
            "content": system_prompt
        })

    payload["messages"].append({
        "role": "user",
        "content": prompt
    })

    # Tell Ollama to return valid JSON for the analysis plan.
    if json_mode:
        payload["format"] = "json"

    try:

        response = requests.post(
            OLLAMA_CHAT_URL,
            json=payload,
            timeout=300
        )

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            "Cannot connect to Ollama.\n\n"
            "Make sure Ollama is running and try:\n"
            "ollama serve"
        )

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "Ollama request timed out."
        )

    # Show useful error instead of a confusing 404
    if response.status_code != 200:

        try:
            error_data = response.json()
        except Exception:
            error_data = response.text

        raise RuntimeError(
            f"Ollama API error {response.status_code}:\n"
            f"{error_data}"
        )

    try:
        data = response.json()
    except Exception:
        raise RuntimeError(
            "Ollama returned an invalid JSON response."
        )

    message = data.get("message", {})

    content = message.get("content", "")

    if not content:
        raise RuntimeError(
            f"Ollama returned no message content.\n"
            f"Response: {data}"
        )

    return content


# ============================================================
# CODE VALIDATION
# ============================================================

ALLOWED_IMPORTS = {
    "pandas",
    "numpy",
    "math"
}

BLOCKED_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "input",
    "system",
    "popen",
    "run",
    "Popen",
    "check_output"
}

BLOCKED_NAMES = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "shutil",
    "pathlib",
    "pickle",
    "builtins",
    "__builtins__"
}


def validate_code(code):

    tree = ast.parse(code, mode="exec")

    for node in ast.walk(tree):

        # Check imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):

            if isinstance(node, ast.Import):
                names = [
                    x.name.split(".")[0]
                    for x in node.names
                ]

            else:
                names = [
                    node.module.split(".")[0]
                ] if node.module else []

            if any(
                name not in ALLOWED_IMPORTS
                for name in names
            ):
                raise ValueError(
                    "Only pandas, numpy and math imports are allowed."
                )

        # Check dangerous calls
        if isinstance(node, ast.Call):

            if (
                isinstance(node.func, ast.Name)
                and node.func.id in BLOCKED_CALLS
            ):
                raise ValueError(
                    f"Blocked function: {node.func.id}"
                )

            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in BLOCKED_CALLS
            ):
                raise ValueError(
                    f"Blocked call: {node.func.attr}"
                )

        # Check dangerous names
        if isinstance(node, ast.Name):

            if node.id in BLOCKED_NAMES:
                raise ValueError(
                    f"Blocked name: {node.id}"
                )

        # Block dunder access
        if isinstance(node, ast.Attribute):

            if node.attr.startswith("__"):
                raise ValueError(
                    "Dunder attribute access is not allowed."
                )

    if not re.search(
        r"\bresult\s*=",
        code
    ):
        raise ValueError(
            "Generated code must assign the final answer to `result`."
        )


# ============================================================
# EXECUTE GENERATED PYTHON
# ============================================================

def execute_code(code, dataframes):

    validate_code(code)

    with tempfile.TemporaryDirectory() as tmp:

        tmp_path = Path(tmp)

        code_path = tmp_path / "analysis.py"

        data_path = tmp_path / "data.pkl"

        # Save dataframes
        pd.to_pickle(
            dataframes,
            data_path
        )

        dataframe_assignments = "\n".join(
            [
                f"{name} = dataframes[{name!r}]"
                for name in dataframes.keys()
            ]
        )

        runner = f"""
import pandas as pd
import numpy as np
import math
import pickle

with open(
    r"{data_path.as_posix()}",
    "rb"
) as f:
    dataframes = pickle.load(f)

{dataframe_assignments}

{code}

print("__VERIFIED_RESULT__")
print(repr(result))
"""

        code_path.write_text(
            runner,
            encoding="utf-8"
        )

        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8"
        }

        proc = subprocess.run(
            [
                sys.executable,
                str(code_path)
            ],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT
        )

        if proc.returncode != 0:

            raise RuntimeError(
                proc.stderr[-4000:]
                or "Analysis process failed."
            )

        marker = "__VERIFIED_RESULT__"

        if marker not in proc.stdout:

            raise RuntimeError(
                "The analysis did not produce a verified result."
            )

        raw = proc.stdout.split(
            marker,
            1
        )[1].strip()

        return raw, proc.stdout


def parse_result(raw):

    try:
        return ast.literal_eval(raw)

    except Exception:
        return raw


# ============================================================
# FILE LOADING
# ============================================================

def safe_name(value):

    return (
        re.sub(
            r"\W+",
            "_",
            str(value)
        )
        .strip("_")
        .lower()
        or "data"
    )


def load_uploaded_files(uploaded_files):

    frames = {}

    pdf_text = []

    for uploaded in uploaded_files:

        suffix = Path(
            uploaded.name
        ).suffix.lower()

        stem = safe_name(
            Path(uploaded.name).stem
        )

        # ---------------- CSV ----------------

        if suffix == ".csv":

            df = pd.read_csv(uploaded)

            frames[stem] = df

        # ---------------- Excel ----------------

        elif suffix in {".xlsx", ".xls"}:

            excel = pd.ExcelFile(uploaded)

            for sheet in excel.sheet_names:

                df = pd.read_excel(
                    uploaded,
                    sheet_name=sheet
                )

                sheet_name = safe_name(sheet)

                key = f"{stem}_{sheet_name}"

                frames[key] = df

        # ---------------- PDF ----------------

        elif suffix == ".pdf":

            if pdfplumber is None:

                raise RuntimeError(
                    "Install pdfplumber:\n"
                    "pip install pdfplumber"
                )

            raw_bytes = uploaded.getvalue()

            with pdfplumber.open(
                io.BytesIO(raw_bytes)
            ) as pdf:

                for page_no, page in enumerate(
                    pdf.pages,
                    start=1
                ):

                    text = page.extract_text() or ""

                    if text:

                        pdf_text.append(
                            f"[{uploaded.name} - page {page_no}]\n"
                            f"{text}"
                        )

                    # Extract PDF tables
                    tables = (
                        page.extract_tables()
                        or []
                    )

                    for table_no, table in enumerate(
                        tables,
                        start=1
                    ):

                        if table and len(table) >= 2:

                            header = [
                                str(x or "").strip()
                                for x in table[0]
                            ]

                            rows = table[1:]

                            if any(header):

                                try:

                                    df = pd.DataFrame(
                                        rows,
                                        columns=header
                                    )

                                    key = (
                                        f"{stem}_"
                                        f"p{page_no}_"
                                        f"table{table_no}"
                                    )

                                    frames[key] = df

                                except Exception:
                                    pass

        else:

            st.warning(
                f"Skipped unsupported file: {uploaded.name}"
            )

    return (
        frames,
        "\n\n".join(pdf_text)
    )


# ============================================================
# BUILD LLM DATA CONTEXT
# ============================================================

def build_data_context(
    frames,
    pdf_text
):

    parts = []

    for name, df in frames.items():

        info = (
            f"DATAFRAME: {name}\n"
            f"ROWS: {len(df)}\n"
            f"COLUMNS: {list(df.columns)}\n"
            f"TYPES: {df.dtypes.astype(str).to_dict()}\n"
            f"PREVIEW:\n"
            f"{dataframe_preview(df)}"
        )

        parts.append(info)

    if pdf_text:

        parts.append(
            "PDF TEXT:\n"
            + pdf_text[:30000]
        )

    return "\n\n---\n\n".join(parts)


# ============================================================
# ASK LLAMA 3.2 TO CREATE ANALYSIS PLAN
# ============================================================

def ask_llm(
    question,
    context
):

    prompt = f"""
USER QUESTION:
{question}

AVAILABLE DATA:
{context}

Generate the smallest correct pandas analysis needed
to answer the user's question.

Remember:

- Use ONLY the supplied data.
- Never invent values.
- Never hard-code the answer.
- The Python code must calculate the answer.
- The final answer must be stored in `result`.
- The code must print `result`.

Return ONLY JSON.
"""

    response = call_ollama(
        prompt,
        system_prompt=SYSTEM_PROMPT,
        json_mode=True
    )

    return extract_json(response)


# ============================================================
# EXPLAIN VERIFIED RESULT
# ============================================================

def make_explanation(
    question,
    result,
    code,
    context
):

    prompt = f"""
Question:
{question}

Verified Python result:
{result!r}

Executed Python code:
{code}

Explain the result in 2-4 simple sentences.

IMPORTANT:

The Python result is authoritative.

Do NOT recalculate the answer.

Do NOT invent information.

Do not provide Python code.

Just explain what the verified result means.
"""

    response = call_ollama(
        prompt
    )

    return response.strip()


# ============================================================
# UI
# ============================================================

st.title(
    "🔎 Verified Data Agent"
)

st.caption(
    "Ask questions about CSV, Excel, and PDF data. "
    "Llama 3.2 generates the analysis and Python "
    "executes it to verify the result."
)


# ============================================================
# SESSION STATE
# ============================================================

if "result" not in st.session_state:

    st.session_state.result = None


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("1. Upload data")

    files = st.file_uploader(
        "CSV, Excel, or PDF",
        type=[
            "csv",
            "xlsx",
            "xls",
            "pdf"
        ],
        accept_multiple_files=True
    )

    st.divider()

    st.header("2. Llama 3.2")

    st.caption(
        f"Model: {OLLAMA_MODEL}"
    )

    st.caption(
        f"Ollama: {OLLAMA_BASE_URL}"
    )

    # Check Ollama
    running, model_found, installed_models = (
        check_ollama()
    )

    if not running:

        st.error(
            "❌ Ollama is not running"
        )

        st.code(
            "ollama serve",
            language="bash"
        )

    elif not model_found:

        st.warning(
            f"⚠️ Model '{OLLAMA_MODEL}' "
            "is not installed."
        )

        st.code(
            f"ollama pull {OLLAMA_MODEL}",
            language="bash"
        )

        if installed_models:

            st.caption(
                "Installed models:"
            )

            for model in installed_models:

                st.write(
                    f"• {model}"
                )

    else:

        st.success(
            "✅ Llama 3.2 is ready"
        )


# ============================================================
# NO FILES
# ============================================================

if not files:

    st.info(
        "Upload one or more files to begin."
    )

    st.markdown(
        """
### Example questions

- What is the total sales?
- Which customer spent the most?
- What was the average order value?
- Compare 2024 revenue with 2025 revenue.
- How many orders came from Chennai?
- What is the highest selling product?
- What is the average sales per customer?

If the data does not contain enough information,
the agent will say so.
"""
    )

    st.stop()


# ============================================================
# LOAD FILES
# ============================================================

try:

    frames, pdf_text = load_uploaded_files(
        files
    )

except Exception as e:

    st.error(
        f"Could not read the files: {e}"
    )

    st.stop()


if not frames and not pdf_text:

    st.error(
        "No usable data was found."
    )

    st.stop()


# ============================================================
# SHOW LOADED DATA
# ============================================================

st.subheader(
    "Loaded data"
)

if frames:

    cols = st.columns(
        min(
            max(len(frames), 1),
            4
        )
    )

    for i, (name, df) in enumerate(
        frames.items()
    ):

        with cols[i % len(cols)]:

            st.metric(
                name,
                f"{len(df):,} rows"
            )

            st.caption(
                ", ".join(
                    map(
                        str,
                        df.columns
                    )
                )
            )


with st.expander(
    "Preview loaded tables"
):

    for name, df in frames.items():

        st.markdown(
            f"**{name}**"
        )

        st.dataframe(
            df.head(10),
            use_container_width=True
        )


# ============================================================
# QUESTION
# ============================================================

question = st.text_area(
    "Ask a question",
    placeholder=(
        "Example: What is the total revenue "
        "from customers in Chennai?"
    ),
    height=90
)


# ============================================================
# ANALYZE
# ============================================================

if st.button(
    "Analyze",
    type="primary",
    disabled=not question.strip()
):

    # Check Ollama
    running, model_found, installed_models = (
        check_ollama()
    )

    if not running:

        st.error(
            "Ollama is not running.\n\n"
            "Start it with:\n"
            "ollama serve"
        )

        st.stop()


    if not model_found:

        st.error(
            f"The model '{OLLAMA_MODEL}' "
            "is not installed."
        )

        st.code(
            f"ollama pull {OLLAMA_MODEL}",
            language="bash"
        )

        st.stop()


    # Build context
    context = build_data_context(
        frames,
        pdf_text
    )


    # --------------------------------------------------------
    # ASK LLAMA
    # --------------------------------------------------------

    with st.spinner(
        "Llama 3.2 is analyzing the data..."
    ):

        try:

            plan = ask_llm(
                question,
                context
            )

        except Exception as e:

            st.error(
                "❌ Llama request failed"
            )

            st.code(
                str(e)
            )

            st.info(
                "Make sure Ollama is running and "
                "that llama3.2 is installed."
            )

            st.stop()


    # --------------------------------------------------------
    # AGENT DECISION
    # --------------------------------------------------------

    st.subheader(
        "Agent decision"
    )

    if not plan.get(
        "can_answer",
        False
    ):

        st.warning(
            "I can't determine this reliably "
            "from the supplied data."
        )

        st.write(
            plan.get(
                "reason",
                "The available evidence is "
                "insufficient or ambiguous."
            )
        )

        st.session_state.result = None

        st.stop()


    # --------------------------------------------------------
    # GET GENERATED CODE
    # --------------------------------------------------------

    code = clean_code(
        plan.get(
            "code",
            ""
        )
    )


    if not code:

        st.error(
            "Llama did not provide executable "
            "verification code."
        )

        st.stop()


    # --------------------------------------------------------
    # VERIFY CODE
    # --------------------------------------------------------

    st.subheader(
        "Verification"
    )

    try:

        raw_result, stdout = execute_code(
            code,
            frames
        )

        verified_result = parse_result(
            raw_result
        )

    except Exception as e:

        st.error(
            "The generated code could not "
            "be verified."
        )

        st.code(
            code,
            language="python"
        )

        st.error(
            str(e)
        )

        st.stop()


    # --------------------------------------------------------
    # EXPLANATION
    # --------------------------------------------------------

    with st.spinner(
        "Llama 3.2 is explaining the verified result..."
    ):

        try:

            explanation = make_explanation(
                question,
                verified_result,
                code,
                context
            )

        except Exception:

            explanation = (
                "The calculation was successfully "
                "executed. See the verified result "
                "and code below."
            )


    # --------------------------------------------------------
    # FINAL RESULT
    # --------------------------------------------------------

    st.success(
        "✅ Verified: the displayed result "
        "comes from executed Python code."
    )


    st.subheader(
        "Answer"
    )

    st.write(
        explanation
    )


    st.metric(
        "Verified result",
        str(verified_result)
    )


    # --------------------------------------------------------
    # VERIFICATION CODE
    # --------------------------------------------------------

    with st.expander(
        "▶ Verification code"
    ):

        st.code(
            code,
            language="python"
        )


    # --------------------------------------------------------
    # EXECUTION OUTPUT
    # --------------------------------------------------------

    with st.expander(
        "▶ Execution output"
    ):

        st.code(
            stdout,
            language="text"
        )


    # --------------------------------------------------------
    # AGENT DECISION DETAILS
    # --------------------------------------------------------

    with st.expander(
        "▶ Agent reasoning decision"
    ):

        st.json(
            {
                "can_answer": plan.get(
                    "can_answer"
                ),
                "answer_type": plan.get(
                    "answer_type"
                ),
                "answer_summary": plan.get(
                    "answer_summary"
                ),
                "reason": plan.get(
                    "reason"
                )
            }
        )


    st.caption(
        "Important: this prototype runs generated "
        "Python code locally. For deployment, use "
        "a stronger isolated sandbox/container."
    )