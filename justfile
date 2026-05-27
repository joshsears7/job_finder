python := "/opt/anaconda3/bin/python3"

default:
    @just --list

# Launch the Streamlit app
app:
    streamlit run app.py

# Run the FastAPI server
api:
    {{python}} api.py

# Score a resume against a job description (interactive)
score:
    {{python}} -c "from claude_ai import CareerIQ; c = CareerIQ(); print(c.score_resume())"

# Scan for new Charlotte-area jobs
scan:
    {{python}} charlotte_jobs.py

# Run background job scanner
bg-scan:
    {{python}} background_scanner.py

# AB testing stats
ab:
    {{python}} ab_testing.py

# Analytics dashboard data
analytics:
    {{python}} analytics.py

# Run linter
lint:
    ruff check . && ruff format --check .

# Format code
fmt:
    ruff format . && echo "formatted"

# Backup project
save:
    bash backup.sh
