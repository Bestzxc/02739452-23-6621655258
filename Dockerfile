FROM apache/airflow:2.10.5-python3.11
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /requirements.txt
# ติดตั้ง extension httpfs ไว้ใน image ล่วงหน้า (ใช้อ่าน Overture Maps จาก S3)
RUN python -c "import duckdb; duckdb.sql('INSTALL httpfs')"
