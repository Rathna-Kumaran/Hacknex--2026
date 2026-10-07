<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verified Data Agent 🔎</title>
  <style>
    :root {
      --primary: #10b981;
      --primary-dark: #059669;
      --bg: #0f172a;
      --card-bg: #1e293b;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --code-bg: #020617;
      --border: #334155;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }

    .container {
      max-width: 900px;
      margin: 0 auto;
    }

    header {
      margin-bottom: 2.5rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
    }

    h1 {
      font-size: 2.25rem;
      color: #ffffff;
      margin-bottom: 0.5rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .description {
      font-size: 1.1rem;
      color: var(--text-muted);
    }

    section {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
    }

    h2 {
      font-size: 1.35rem;
      margin-bottom: 1rem;
      color: var(--primary);
    }

    ul {
      list-style-type: none;
    }

    li {
      margin-bottom: 0.75rem;
      padding-left: 1.25rem;
      position: relative;
    }

    li::before {
      content: "•";
      color: var(--primary);
      font-weight: bold;
      position: absolute;
      left: 0;
    }

    /* Workflow Diagram */
    .workflow {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      align-items: center;
      margin: 1rem 0;
    }

    .workflow-step {
      background: var(--bg);
      border: 1px solid var(--border);
      padding: 0.6rem 1.2rem;
      border-radius: 6px;
      font-weight: 600;
      width: 100%;
      max-width: 380px;
      text-align: center;
      color: var(--text);
    }

    .workflow-arrow {
      color: var(--primary);
      font-weight: bold;
    }

    /* Code Blocks */
    pre {
      background-color: var(--code-bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 1rem;
      overflow-x: auto;
      font-family: "Fira Code", Monaco, Consolas, monospace;
      font-size: 0.9rem;
      color: #38bdf8;
      margin-top: 0.5rem;
    }

    code {
      font-family: "Fira Code", Monaco, Consolas, monospace;
      background: var(--code-bg);
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
      font-size: 0.875rem;
      color: #38bdf8;
    }

    .env-note {
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-top: 0.5rem;
      font-style: italic;
    }
  </style>
</head>
<body>

  <div class="container">
    <header>
      <h1>Verified Data Agent 🔎</h1>
      <p class="description">
        A Streamlit application that answers questions over uploaded CSV, Excel, and PDF data by using Google Gemini to generate Pandas code and executing it locally to verify all analytical results.
      </p>
    </header>

    <!-- Key Features -->
    <section>
      <h2>🌟 Key Features</h2>
      <ul>
        <li><strong>Multi-Format Data Support:</strong> Ingests CSV (<code>.csv</code>), Excel (<code>.xlsx</code>, <code>.xls</code>), and PDF (<code>.pdf</code>) files with automatic extraction of tables and plain text.</li>
        <li><strong>Strict Data Grounding:</strong> Configured with system instructions to rely strictly on supplied data and refuse hallucinated or unverifiable answers.</li>
        <li><strong>Executable Verification:</strong> Generates pure Pandas/Python code to compute answers rather than predicting raw numerical values directly.</li>
        <li><strong>AST Code Safety Validation:</strong> Validates generated code using Python's Abstract Syntax Tree (<code>ast</code>) to block unauthorized imports, system execution, and dangerous built-ins (<code>eval</code>, <code>exec</code>, <code>open</code>, <code>os</code>, <code>subprocess</code>).</li>
        <li><strong>Sandboxed Subprocess Execution:</strong> Executes code in an isolated subprocess with explicit timeout safeguards and Pandas pickle deserialization.</li>
        <li><strong>API Retry & Fallback:</strong> Includes automated retry logic with exponential backoff for Gemini API rate limits (status codes 429, 500, 502, 503, 504) and fallback model support.</li>
      </ul>
    </section>

    <!-- Workflow -->
    <section>
      <h2>🔄 Workflow</h2>
      <div class="workflow">
        <div class="workflow-step">Upload CSV / Excel / PDF</div>
        <div class="workflow-arrow">▼</div>
        <div class="workflow-step">Pandas / pdfplumber Extraction</div>
        <div class="workflow-arrow">▼</div>
        <div class="workflow-step">Gemini Generates Pandas Code</div>
        <div class="workflow-arrow">▼</div>
        <div class="workflow-step">AST Safety Code Inspector</div>
        <div class="workflow-arrow">▼</div>
        <div class="workflow-step">Subprocess Execution & Verification</div>
        <div class="workflow-arrow">▼</div>
        <div class="workflow-step">Gemini Explains Executed Result</div>
      </div>
    </section>

    <!-- Repository Structure -->
    <section>
      <h2>📁 Repository Structure</h2>
      <pre>.
├── app.py              # Main Streamlit application and execution agent
├── requirements.txt    # Project dependencies
├── .env.example        # Environment variable template
└── README.md           # Project documentation</pre>
    </section>

    <!-- Requirements -->
    <section>
      <h2>⚙️ Requirements</h2>
      <ul>
        <li><strong>Python:</strong> 3.9 or higher</li>
        <li><strong>Gemini API Key:</strong> Obtain a key from Google AI Studio.</li>
      </ul>
    </section>

    <!-- Getting Started -->
    <section>
      <h2>🚀 Getting Started</h2>
      
      <p><strong>1. Clone the Repository</strong></p>
      <pre>git clone https://github.com/your-username/verified-data-agent.git
cd verified-data-agent</pre>

      <br>
      <p><strong>2. Create and Activate Virtual Environment</strong></p>
      <p>Windows:</p>
      <pre>python -m venv .venv
.venv\Scripts\activate</pre>
      
      <p style="margin-top:0.5rem;">macOS/Linux:</p>
      <pre>python3 -m venv .venv
source .venv/bin/activate</pre>

      <br>
      <p><strong>3. Install Dependencies</strong></p>
      <p>Create a <code>requirements.txt</code> file with:</p>
      <pre>streamlit
pandas
requests
pdfplumber
python-dotenv
openpyxl</pre>
      
      <p style="margin-top:0.5rem;">Then install:</p>
      <pre>pip install -r requirements.txt</pre>
    </section>

    <!-- Environment Configuration -->
    <section>
      <h2>🔑 Environment Configuration</h2>
      <p>Create a <code>.env</code> file in the root directory:</p>
      <pre>GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash</pre>
      <p class="env-note">Note: You can also leave GEMINI_API_KEY empty in .env and enter your API key directly in the Streamlit app sidebar.</p>
    </section>

    <!-- Running the App -->
    <section>
      <h2>💻 Running the App</h2>
      <p>Launch the Streamlit application:</p>
      <pre>streamlit run app.py</pre>
      <p style="margin-top:0.5rem;">Open <code>http://localhost:8501</code> in your browser.</p>
    </section>
  </div>

</body>
</html>
