
# Verified Data Agent

A Streamlit prototype for answering questions over messy CSV, Excel, and PDF data.

Workflow:

Upload CSV/PDF
→ Pandas/PDF extraction
→ LLM understands the question
→ LLM generates Pandas code
→ code is validated
→ code is executed locally
→ executed result becomes the answer
→ LLM explains the verified result

## 1. Install

Use Python 3.10+.

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
```

## 2. Configure the API key

Copy `.env.example` to `.env` and put your API key there:

```text
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-6.1-sol
```

You can change `OPENAI_MODEL` to another model available to your API account.

## 3. Run

```bash
streamlit run app.py
```

Open the local Streamlit address shown in the terminal.

## 4. Try this data

Create `sales.csv`:

```csv
Customer_ID,City,Amount
1,Chennai,1200
2,Bangalore,800
3,Chennai,1500
4,Chennai,700
```

Upload it and ask:

`What is the total amount spent by customers from Chennai?`

The expected verified result is 3400.

## 5. Why this is safer than normal LLM arithmetic

The model is NOT trusted to perform the final arithmetic.

It proposes code such as:

```python
result = orders.loc[orders["City"] == "Chennai", "Amount"].sum()
print(result)
```

The application executes the code and displays the execution result.

If the model cannot establish that the data supports the answer, it is instructed to return `can_answer=false`.

## Important security note

The included code validator is a hackathon prototype, not a production-grade security sandbox. For deployment, execute generated code in a dedicated isolated container/VM with:

- no network access
- CPU and memory limits
- read-only input data
- a non-root user
- filesystem restrictions
- process/time limits
- an allowlist of Python libraries

Never run arbitrary model-generated code directly on a sensitive production machine.
"# Hacknex--2026" 
