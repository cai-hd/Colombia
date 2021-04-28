FROM python:3.8.9-slim
WORKDIR /app
COPY . /app
RUN pip install -r requirements.txt
CMD ["python","app.py"]