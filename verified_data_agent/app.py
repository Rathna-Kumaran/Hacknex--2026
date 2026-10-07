import os
import re
import io
import json
import ast
import tempfile
import subprocess
import sys
import time
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

st.set_page_config(
    page_title="Verified Data Agent",
    page_icon="🔎",
    layout="wide"
)

# ---------------------------------------------------------------
# Gemini configuration
# ---------------------------------------------------------------
GEMINI_API_KEY_ENV = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or ""
)
GEMINI_MODEL = (
    os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    .strip()
    .strip('"')
    .strip("'")
    .lower()
)
if GEMINI_MODEL.startswith("models/"):
    GEMINI_MODEL = GEMINI_MODEL[len("models/"):]

# Optional: a second model to try if the main one stays overloaded
GEMINI_FALLBACK_MODEL = (
    os.getenv("GEMINI_FALLBACK_MODEL", "").strip().strip('"').strip("'").lower()
)
MAX_RETRIES = 4                      # attempts per model
RETRY_STATUS = {429, 500, 502, 503, 504}
GEMINI_BASE_URL = os.getenv(
    "GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta"
).rstrip("/")

MAX_ROWS_IN_PROMPT = 30
EXEC_TIMEOUT = 8

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


def get_api_key():
    """API key from the sidebar field (if filled) or from the environment."""
    key = (
        st.session_state.get("gemini_key_input", "").strip()
        or GEMINI_API_KEY_ENV
    )
    # Tolerate stray whitespace or quotes copied into .env
    return key.strip().strip('"').strip("'").strip()


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
    Extract JSON from the Gemini response.
    """
    if not text:
        raise ValueError("Gemini returned an empty response.")
    text = text.strip()

    # Strip markdown fences if the model added them
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise ValueError(
        "Gemini did not return valid JSON.\n\n"
        f"Raw response:\n{text}"
    )


def check_gemini():
    """
    Check whether an API key is set and the requested model is available.
    Returns (key_present, key_valid_and_model_found, message).
    """
    api_key = get_api_key()
    if not api_key:
        return False, False, "No API key set."

    headers = {"x-goog-api-key": api_key}

    def google_message(resp):
        try:
            return resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            return resp.text[:300]

    try:
        # 1) Test the key on its own, independent of the model name
        key_resp = requests.get(
            f"{GEMINI_BASE_URL}/models",
            headers=headers,
            params={"pageSize": 1},
            timeout=10
        )
        if key_resp.status_code != 200:
            return (
                True,
                False,
                f"API key problem ({key_resp.status_code}): "
                f"{google_message(key_resp)}"
            )

        # 2) Key is fine, now test the model
        model_resp = requests.get(
            f"{GEMINI_BASE_URL}/models/{GEMINI_MODEL}",
            headers=headers,
            timeout=10
        )
    except requests.exceptions.RequestException as e:
        return True, False, f"Could not reach Gemini API: {e}"

    if model_resp.status_code == 200:
        return True, True, "OK"
    return (
        True,
        False,
        f"Key works, but model '{GEMINI_MODEL}' is unavailable "
        f"({model_resp.status_code}): {google_message(model_resp)}"
    )


def call_gemini(prompt, system_prompt=None, json_mode=False):
    """
    Call the Gemini generateContent REST endpoint.
    """
    api_key = get_api_key()
    if not api_key:
        raise RuntimeError(
            "No Gemini API key found.\n\n"
            "Set GEMINI_API_KEY in your environment/.env file "
            "or enter it in the sidebar."
        )

    generation_config = {"temperature": 0}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": generation_config
    }
    if system_prompt:
        payload["systemInstruction"] = {
            "parts": [{"text": system_prompt}]
        }

    models_to_try = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models_to_try.append(GEMINI_FALLBACK_MODEL)

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    response = None
    for model_name in models_to_try:
        url = f"{GEMINI_BASE_URL}/models/{model_name}:generateContent"

        for attempt in range(MAX_RETRIES):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=120
                )
            except requests.exceptions.ConnectionError:
                raise RuntimeError(
                    "Cannot connect to the Gemini API. "
                    "Check your internet connection."
                )
            except requests.exceptions.Timeout:
                response = None
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                break

            # Success or a non-temporary error: stop retrying
            if response.status_code not in RETRY_STATUS:
                break

            # Temporary overload: wait 1s, 2s, 4s ... then try again
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)

        # Got a usable (non-overloaded) response from this model
        if response is not None and response.status_code not in RETRY_STATUS:
            break

    if response is None:
        raise RuntimeError("Gemini request timed out.")

    if response.status_code != 200:
        try:
            error_data = response.json()
        except Exception:
            error_data = response.text
        raise RuntimeError(
            f"Gemini API error {response.status_code}:\n"
            f"{error_data}"
        )

    try:
        data = response.json()
    except Exception:
        raise RuntimeError("Gemini returned an invalid JSON response.")

    # Prompt blocked before generation
    feedback = data.get("promptFeedback", {})
    if feedback.get("blockReason"):
        raise RuntimeError(
            f"Gemini blocked the prompt: {feedback['blockReason']}"
        )

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(
            f"Gemini returned no candidates.\nResponse: {data}"
        )

    parts = candidates[0].get("content", {}).get("parts", [])
    content = "".join(
        p.get("text", "")
        for p in parts
        if not p.get("thought")
    )

    if not content:
        finish = candidates[0].get("finishReason", "unknown")
        raise RuntimeError(
            f"Gemini returned no text content "
            f"(finishReason: {finish})."
        )
    return content


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
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                names = [x.name.split(".")[0] for x in node.names]
            else:
                names = [node.module.split(".")[0]] if node.module else []

            if any(name not in ALLOWED_IMPORTS for name in names):
                raise ValueError(
                    "Only pandas, numpy and math imports are allowed."
                )

        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in BLOCKED_CALLS
            ):
                raise ValueError(f"Blocked function: {node.func.id}")

            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in BLOCKED_CALLS
            ):
                raise ValueError(f"Blocked call: {node.func.attr}")

        if isinstance(node, ast.Name):
            if node.id in BLOCKED_NAMES:
                raise ValueError(f"Blocked name: {node.id}")

        if isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                raise ValueError(
                    "Dunder attribute access is not allowed."
                )

    if not re.search(r"\bresult\s*=", code):
        raise ValueError(
            "Generated code must assign the final answer to `result`."
        )


def execute_code(code, dataframes):
    validate_code(code)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        code_path = tmp_path / "analysis.py"
        data_path = tmp_path / "data.pkl"

        pd.to_pickle(dataframes, data_path)

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
        code_path.write_text(runner, encoding="utf-8")

        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONIOENCODING": "utf-8"
        }

        proc = subprocess.run(
            [sys.executable, str(code_path)],
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT
        )

        if proc.returncode != 0:
            raise RuntimeError(
                proc.stderr[-4000:] or "Analysis process failed."
            )

        marker = "__VERIFIED_RESULT__"
        if marker not in proc.stdout:
            raise RuntimeError(
                "The analysis did not produce a verified result."
            )

        raw = proc.stdout.split(marker, 1)[1].strip()
        return raw, proc.stdout


def parse_result(raw):
    try:
        return ast.literal_eval(raw)
    except Exception:
        return raw


def safe_name(value):
    return (
        re.sub(r"\W+", "_", str(value)).strip("_").lower()
        or "data"
    )


def load_uploaded_files(uploaded_files):
    frames = {}
    pdf_text = []

    for uploaded in uploaded_files:
        suffix = Path(uploaded.name).suffix.lower()
        stem = safe_name(Path(uploaded.name).stem)

        if suffix == ".csv":
            df = pd.read_csv(uploaded)
            frames[stem] = df

        elif suffix in {".xlsx", ".xls"}:
            excel = pd.ExcelFile(uploaded)
            for sheet in excel.sheet_names:
                df = pd.read_excel(excel, sheet_name=sheet)
                sheet_name = safe_name(sheet)
                key = f"{stem}_{sheet_name}"
                frames[key] = df

        elif suffix == ".pdf":
            if pdfplumber is None:
                raise RuntimeError(
                    "Install pdfplumber:\n"
                    "pip install pdfplumber"
                )

            raw_bytes = uploaded.getvalue()
            with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
                for page_no, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    if text:
                        pdf_text.append(
                            f"[{uploaded.name} - page {page_no}]\n"
                            f"{text}"
                        )

                    tables = page.extract_tables() or []
                    for table_no, table in enumerate(tables, start=1):
                        if table and len(table) >= 2:
                            header = [
                                str(x or "").strip()
                                for x in table[0]
                            ]
                            rows = table[1:]
                            if any(header):
                                try:
                                    df = pd.DataFrame(rows, columns=header)
                                    key = (
                                        f"{stem}_"
                                        f"p{page_no}_"
                                        f"table{table_no}"
                                    )
                                    frames[key] = df
                                except Exception:
                                    pass
        else:
            st.warning(f"Skipped unsupported file: {uploaded.name}")

    return frames, "\n\n".join(pdf_text)


def build_data_context(frames, pdf_text):
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
        parts.append("PDF TEXT:\n" + pdf_text[:30000])

    return "\n\n---\n\n".join(parts)


def ask_llm(question, context):
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
    response = call_gemini(
        prompt,
        system_prompt=SYSTEM_PROMPT,
        json_mode=True
    )
    return extract_json(response)


def make_explanation(question, result, code, context):
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
    response = call_gemini(prompt)
    return response.strip()


# ---------------------------------------------------------------
# UI
# ---------------------------------------------------------------
st.title("🔎 Verified Data Agent")
st.caption(
    "Ask questions about CSV, Excel, and PDF data. "
    "Gemini generates the analysis and Python "
    "executes it to verify the result."
)

if "result" not in st.session_state:
    st.session_state.result = None

with st.sidebar:
    st.header("1. Upload data")
    files = st.file_uploader(
        "CSV, Excel, or PDF",
        type=["csv", "xlsx", "xls", "pdf"],
        accept_multiple_files=True
    )

    st.divider()
    st.header("2. Gemini")
    st.caption(f"Model: {GEMINI_MODEL}")

    st.text_input(
        "Gemini API key",
        type="password",
        key="gemini_key_input",
        placeholder="Leave blank to use GEMINI_API_KEY env var",
        help="Get a key at https://aistudio.google.com/apikey"
    )

    key_present, gemini_ready, gemini_msg = check_gemini()

    if not key_present:
        st.error("❌ No Gemini API key")
        st.code("GEMINI_API_KEY=your_key_here", language="bash")
    elif not gemini_ready:
        st.warning(f"⚠️ {gemini_msg}")
    else:
        st.success(f"✅ {GEMINI_MODEL} is ready")

if not files:
    st.info("Upload one or more files to begin.")
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

try:
    frames, pdf_text = load_uploaded_files(files)
except Exception as e:
    st.error(f"Could not read the files: {e}")
    st.stop()

if not frames and not pdf_text:
    st.error("No usable data was found.")
    st.stop()

st.subheader("Loaded data")

if frames:
    cols = st.columns(min(max(len(frames), 1), 4))
    for i, (name, df) in enumerate(frames.items()):
        with cols[i % len(cols)]:
            st.metric(name, f"{len(df):,} rows")
            st.caption(", ".join(map(str, df.columns)))

with st.expander("Preview loaded tables"):
    for name, df in frames.items():
        st.markdown(f"**{name}**")
        st.dataframe(df.head(10), use_container_width=True)

question = st.text_area(
    "Ask a question",
    placeholder=(
        "Example: What is the total revenue "
        "from customers in Chennai?"
    ),
    height=90
)

if st.button(
    "Analyze",
    type="primary",
    disabled=not question.strip()
):
    key_present, gemini_ready, gemini_msg = check_gemini()

    if not key_present:
        st.error(
            "No Gemini API key found. Set GEMINI_API_KEY "
            "or enter it in the sidebar."
        )
        st.stop()

    if not gemini_ready:
        st.error(gemini_msg)
        st.stop()

    context = build_data_context(frames, pdf_text)

    with st.spinner("Gemini is analyzing the data..."):
        try:
            plan = ask_llm(question, context)
        except Exception as e:
            st.error("❌ Gemini request failed")
            st.code(str(e))
            st.info(
                "Check your API key, model name, "
                "and internet connection."
            )
            st.stop()

    st.subheader("Agent decision")

    if not plan.get("can_answer", False):
        st.warning(
            "I can't determine this reliably "
            "from the supplied data."
        )
        st.write(
            plan.get(
                "reason",
                "The available evidence is insufficient or ambiguous."
            )
        )
        st.session_state.result = None
        st.stop()

    code = clean_code(plan.get("code", ""))

    if not code:
        st.error("Gemini did not provide executable verification code.")
        st.stop()

    st.subheader("Verification")

    try:
        raw_result, stdout = execute_code(code, frames)
        verified_result = parse_result(raw_result)
    except Exception as e:
        st.error("The generated code could not be verified.")
        st.code(code, language="python")
        st.error(str(e))
        st.stop()

    with st.spinner("Gemini is explaining the verified result..."):
        try:
            explanation = make_explanation(
                question,
                verified_result,
                code,
                context
            )
        except Exception:
            explanation = (
                "The calculation was successfully executed. "
                "See the verified result and code below."
            )

    st.success(
        "✅ Verified: the displayed result "
        "comes from executed Python code."
    )

    st.subheader("Answer")
    st.write(explanation)
    st.metric("Verified result", str(verified_result))

    with st.expander("▶ Verification code"):
        st.code(code, language="python")

    with st.expander("▶ Execution output"):
        st.code(stdout, language="text")

    with st.expander("▶ Agent reasoning decision"):
        st.json(
            {
                "can_answer": plan.get("can_answer"),
                "answer_type": plan.get("answer_type"),
                "answer_summary": plan.get("answer_summary"),
                "reason": plan.get("reason")
            }
        )

    st.caption(
        "Important: this prototype runs generated "
        "Python code locally. For deployment, use "
        "a stronger isolated sandbox/container."
    )
