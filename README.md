# Instamart Customer Intelligence & Support Copilot — Capstone Project Title

> A simple educational implementation of the supplied fictional Instamart capstone. All records are synthetic. The project uses an offline mock language model and does not require an API key, paid service or real Instamart data.

## Learning outcomes

This project demonstrates how to (1) load and audit CSV data, (2) clean data and store it in SQLite, (3) analyse data using SQL and pandas, (4) segment customers and predict possible lapses, (5) protect personal information and classify support tickets, and (6) retrieve policy information and run a controlled refund workflow.

## Setup and run

Python 3.11–3.13 is recommended for the pinned project dependencies. Run these commands from the project root folder.

```bash
python -m venv .venv

# Windows PowerShell:
.venv\Scripts\Activate.ps1

# macOS/Linux:
# source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python generate_data.py
python run_pipeline.py
```

The `run_pipeline.py` script runs Parts A, B, C and D in order. Part A prints `ALL CHECKPOINTS PASSED` when its required validation checks succeed.

To open the dashboard after the pipeline finishes, start the local server:

```bash
python src/api/server.py
```

Open `http://127.0.0.1:8000/` in your browser. The dashboard has four pages: Executive Overview, Customer Intelligence, AI Policy Assistant and Project Monitoring. No separate frontend installation is required.

## Repository map

- `generate_data.py`: creates the fictional customers, products, orders, tickets and policy files.
- `mock_llm.py`: offline simulator used for ticket classification, policy answers and agent tool calls.
- `run_pipeline.py`: runs all four project parts in the required order.
- `src/part_a.py`: audits and cleans data, creates the SQLite database and runs SQL analysis.
- `src/part_b.py`: performs RFM analysis, customer segmentation and lapse prediction.
- `src/part_c.py`: redacts personal details, classifies tickets and routes them.
- `src/part_d.py`: implements policy retrieval and the refund agent.
- `src/api/server.py`: provides the local API and serves the dashboard.
- `frontend/`: HTML, CSS and JavaScript files for the four dashboard pages.
- `sql/queries.sql`: contains the seven required SQL queries.
- `data/`: contains raw and cleaned CSV files, policy documents and the SQLite database.
- `outputs/`: contains generated reports, model files and processing results.
- `state/`: stores refund-agent checkpoint information.

## How to follow the data workflow

1. Run `generate_data.py` to create the synthetic CSV files and policy documents.
2. Load the raw CSV files and inspect their shapes, data types, missing values, duplicates and invalid values.
3. Clean the customer, product and order data using the documented rules.
4. Save the cleaned data as CSV files and load the tables into SQLite.
5. Validate the cleaned data before using it for customer modelling, ticket triage or refund processing.

## Part A — Data foundation

Part A audits the raw data, standardises customer information, removes duplicate order records and keeps the latest record for each order. It fills missing order amounts using product prices and imputes missing delivery times only for completed orders. The cleaned data is saved as CSV files and stored in the SQLite database. Seven SQL queries and pandas analysis are also included.

Key results: 1,200 customers, 40 products and 13,084 raw order rows. The cleaned order table contains 12,309 orders: 11,110 completed and 1,199 cancelled. Completed-order revenue is INR 2,998,668.80.

## Part B — Customer segments and lapse prediction

Part B calculates Recency, Frequency and Monetary (RFM) values using completed orders. It applies K-means clustering, compares cluster counts from K=2 to K=8 and uses PCA to examine the customer groups. Four customer segments are created and described.

The lapse model uses order information before 1 September 2025 to predict customers with no completed order during September. Logistic Regression and Random Forest are compared, and the selected model and retention list are saved in `outputs/`.

## Part C — Support ticket triage and privacy

Part C checks for empty and overly long tickets before processing. It masks email addresses, phone numbers and order IDs before sending ticket text to the offline mock model. The pipeline validates model responses, retries temporary failures and uses a keyword fallback when appropriate.

Tickets are routed to the support queue, security team, premium desk or human review according to their category and customer segment.

## Part D — Policy retrieval and refund agent

Part D reads the five policy documents, splits them into overlapping text chunks and uses TF-IDF with cosine similarity to retrieve relevant policy passages. The offline mock model generates answers from the retrieved context and returns a fallback when the information is not available in the policies.

The refund agent uses five tools: `get_order`, `search_policy`, `calculate_refund`, `issue_refund` and `escalate_to_human`. Only completed orders delivered in more than 45 minutes are eligible for a full refund. Refunds above INR 1,000 require human approval. The agent saves its actions and checkpoints locally; it does not make real payments.

## Frontend dashboard

The dashboard uses HTML5, CSS3, vanilla JavaScript and browser-native SVG charts. It contains four pages:

1. **Executive Overview** — customer, order and revenue summary.
2. **Customer Intelligence** — customer segments, RFM information and lapse risk.
3. **AI Policy Assistant** — a chat interface connected to the policy retrieval API.
4. **Project Monitoring** — status and metrics for Parts A, B, C and D.

The frontend gets its information from the local Python API. It does not use a frontend framework or an external chart library.

## GitHub learning resources

These official projects and guides are useful for understanding the libraries used in this capstone:

- [pandas](https://github.com/pandas-dev/pandas) — loading, cleaning and analysing tabular data.
- [scikit-learn](https://github.com/scikit-learn/scikit-learn) — clustering, preprocessing and machine learning.
- [Python tutorial](https://docs.python.org/3/tutorial/) — Python fundamentals.
- [Jupyter Notebook](https://github.com/jupyter/notebook) — notebook-based learning and experiments.
- [SQLite](https://www.sqlite.org/docs.html) — relational database and SQL queries.

## Limitations and next steps

- All customer, order, ticket and policy records are synthetic and fictional.
- `mock_llm.py` is a deterministic offline simulator, not a real language model.
- The lapse model is evaluated on a single synthetic time period; it should be tested on later data before real use.
- The retention list is illustrative and should not be treated as a fully leakage-free evaluation.
- The refund agent is a local simulation and does not connect to a payment gateway.
- A production system would need authentication, access controls, stronger privacy checks, monitoring and a formal human-approval process.
