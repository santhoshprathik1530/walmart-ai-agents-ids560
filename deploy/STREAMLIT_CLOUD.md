# Put the dashboard online for free: Streamlit Community Cloud

Free, made for Streamlit, deploys straight from this GitHub repo and redeploys on every push to `main`.
(Netlify cannot run it: Netlify serves static pages and short functions, and Streamlit needs an always-on Python
server. Hugging Face now charges for Docker/Gradio Spaces.)

## One time (about 2 minutes)

1. Go to https://share.streamlit.io and sign in with the GitHub account that owns this repo.
2. **Create app** → **Deploy a public app from GitHub**:
   - Repository: `santhoshprathik1530/walmart-ai-agents-ids560`, branch `main`
   - Main file path: `app/dashboard.py`
   - App URL: pick a name, for example `ids560-store-sales-assistant`
   - **Advanced settings** → Python version **3.12**
   - Secrets (optional, for **Run the agent** and the chat):
     ```toml
     OPENROUTER_API_KEY = "..."
     LLM_MODEL = "anthropic/claude-haiku-5.5,free"
     ```
     Anyone with the link can then spend this key, so set a credit limit at openrouter.ai/settings/keys.
3. **Deploy**. The first build takes a few minutes. The link is `https://<name>.streamlit.app`.

Without the secret, the site still shows all 127 flagged store-weeks and the agent's saved answers for the Top 20.

## What is in the repo for this

- `app/requirements.txt`: the packages (Streamlit Cloud reads the file next to the main file).
- `.streamlit/config.toml`: the Walmart blue theme (Streamlit Cloud runs from the repo root).
- `app/vectorstore/variants/`: the report-search index the chat and live runs use (setup E), 22 MB.
- Not in the repo: the Kaggle `features.csv` (Kaggle's rules don't allow re-sharing). Live runs online skip fuel price,
  temperature and unemployment. Everything else works.

Apps on the free plan go to sleep after a few days without visits. The first visitor then clicks "Yes, get this app
back up" and waits about a minute.
