FROM python:3.11-slim
WORKDIR /runner
COPY tests/requirements.txt /runner/requirements.txt
RUN pip install --no-cache-dir -r /runner/requirements.txt
COPY tests/run_text_to_sql.py /runner/run_text_to_sql.py
COPY docs/text_to_sql_qa_test_cases.md /runner/text_to_sql_qa_test_cases.md
ENTRYPOINT ["python","/runner/run_text_to_sql.py"]
